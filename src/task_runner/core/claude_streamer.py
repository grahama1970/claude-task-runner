#!/usr/bin/env python3
"""
Claude Streamer Module for Task Runner

This module provides functions for running Claude with real-time output streaming,
using subprocess.Popen for non-blocking execution. It enables visibility into
Claude's progress during task execution and includes context clearing capabilities.

Sample Input:
- Task file path: "/path/to/task.md"
- Result file path: "/path/to/result.txt"
- Error file path: "/path/to/error.txt"
- Claude executable path: "/usr/local/bin/claude"
- Command arguments: ["--no-auth-check"]
- Timeout in seconds: 300

Sample Output:
- Dictionary with execution results:
  {
    "task_file": "/path/to/task.md",
    "result_file": "/path/to/result.txt",
    "error_file": "/path/to/error.txt",
    "exit_code": 0,
    "execution_time": 12.45,
    "success": true,
    "status": "completed",
    "result_size": 1024
  }

Links:
- Claude CLI: https://github.com/anthropics/anthropic-cli
- Loguru Documentation: https://loguru.readthedocs.io/
"""

import sys
import time
import subprocess
import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from loguru import logger


def find_claude_path() -> str:
    """
    Find the Claude executable in the system PATH.
    
    Returns:
        str: Path to the Claude executable
    """
    try:
        which_result = subprocess.run(
            ["which", "claude"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if which_result.returncode == 0:
            path = which_result.stdout.strip()
            if path and os.access(path, os.X_OK):
                return path
    except Exception as e:
        logger.warning(f"Error finding Claude with 'which': {e}")
    
    # Default fallback
    return "claude"


def stream_claude_output(
    task_file: str,
    result_file: Optional[str] = None,
    error_file: Optional[str] = None,
    claude_path: Optional[str] = None,
    cmd_args: Optional[List[str]] = None,
    timeout_seconds: int = 300,
    raw_json: bool = False,
    quiet: bool = False,
    live_layout: Optional[Any] = None,
    update_handler: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Run Claude on a task file and stream its output in real-time using subprocess.Popen.
    
    Args:
        task_file: Path to the task file
        result_file: Path to save the result (defaults to task_file with .result extension)
        error_file: Path to save error output (defaults to task_file with .error extension)
        claude_path: Path to the Claude executable (found automatically if None)
        cmd_args: Additional command-line arguments for Claude
        timeout_seconds: Maximum execution time in seconds
        raw_json: Whether to output raw JSON instead of human-friendly format
        quiet: Whether to suppress console output (still writes to files)
        live_layout: Optional Rich Live object for layout-based display
        update_handler: Function to update the dashboard with streaming content
        
    Returns:
        Dictionary with execution results including success status, time taken, and file paths
    """
    task_path = Path(task_file)
    
    # Set up default output files if not provided
    if result_file is None:
        result_file = str(task_path.with_suffix(".result"))
    
    if error_file is None:
        error_file = str(task_path.with_suffix(".error"))
    
    result_path = Path(result_file)
    error_path = Path(error_file)
    
    # Create parent directories if needed
    result_path.parent.mkdir(exist_ok=True, parents=True)
    error_path.parent.mkdir(exist_ok=True, parents=True)
    
    # Use provided Claude path or find it
    if claude_path is None:
        claude_path = find_claude_path()
    
    # Initialize command args
    if cmd_args is None:
        cmd_args = []
    
    logger.info(f"Task file: {task_file}")
    logger.info(f"Result will be saved to: {result_file}")
    
    # Start the process
    start_time = time.time()
    content = ""
    result = {
        "task_file": task_file,
        "result_file": result_file,
        "error_file": error_file,
        "exit_code": -1,
        "execution_time": 0.0,
        "success": False,
        "status": "failed",
        "result_size": 0
    }
    
    try:
        # Build Claude command
        cmd = [claude_path] + cmd_args + [str(task_path)]
        logger.info(f"Running command: {' '.join(cmd)}")
        
        # Open result and error files
        with open(result_path, 'w', encoding='utf-8') as result_output, \
             open(error_path, 'w', encoding='utf-8') as error_output:
            # Start subprocess
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line-buffered
                universal_newlines=True
            )
            
            logger.info("Started streaming Claude's output...")
            last_output_time = time.time()
            streaming_buffer = []
            
            while True:
                # Check if process has ended
                if process.poll() is not None and not process.stdout.readable():
                    break
                
                # Check for timeout
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    logger.warning(f"Claude process timed out after {timeout_seconds}s")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    content += f"\n\n[TIMEOUT: Claude process was terminated after {timeout_seconds}s]"
                    result_output.write(content)
                    result_output.flush()
                    error_output.write("Timeout occurred\n")
                    error_output.flush()
                    if update_handler:
                        update_handler(content)
                    if live_layout and not quiet:
                        live_layout.update(content)
                    result.update({
                        "status": "timeout",
                        "execution_time": elapsed,
                        "exit_code": -1
                    })
                    return result
                
                # Log silent periods
                if time.time() - last_output_time > 10:
                    logger.info(f"Claude has been silent for {int(time.time() - last_output_time)}s")
                    last_output_time = time.time()
                
                # Read stdout
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        content += line + "\n"
                        result_output.write(line + "\n")
                        result_output.flush()
                        streaming_buffer.append(line + "\n")
                        logger.info(f"Claude: {line[:80]}...")
                        
                        # Handle JSON output
                        if raw_json and line.startswith('{'):
                            try:
                                data = json.loads(line)
                                logger.debug(f"JSON keys: {', '.join(data.keys())}")
                                pretty_json = json.dumps(data, indent=2)
                                result_output.write(pretty_json + "\n")
                                result_output.flush()
                                if 'content' in data:
                                    content_text = data['content']
                                    if isinstance(content_text, str):
                                        if update_handler:
                                            update_handler(content_text)
                                    elif isinstance(content_text, list):
                                        text = "".join(block['text'] for block in content_text 
                                                      if isinstance(block, dict) and block.get('type') == 'text')
                                        if update_handler and text:
                                            update_handler(text)
                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON: {line[:100]}...")
                        
                        # Handle special messages
                        elif "[ERROR]" in line:
                            logger.error(f"Claude error: {line}")
                            error_output.write(line + "\n")
                            error_output.flush()
                        elif any(marker in line for marker in ["Using tool:", "I'll help you with", "I'll answer"]):
                            logger.info(f"Claude: {line}")
                            if update_handler:
                                update_handler(line + "\n")
                            if live_layout and not quiet:
                                live_layout.update(line + "\n")
                        else:
                            # Regular output
                            if update_handler:
                                update_handler(content)
                            if live_layout and not quiet:
                                live_layout.update(content)
                
                # Read stderr
                err_line = process.stderr.readline()
                if err_line:
                    err_line = err_line.strip()
                    if err_line:
                        content += f"\n[ERROR] {err_line}\n"
                        result_output.write(f"\n[ERROR] {err_line}\n")
                        result_output.flush()
                        error_output.write(err_line + "\n")
                        error_output.flush()
                        logger.error(f"Claude error: {err_line}")
                        if update_handler:
                            update_handler(content)
                        if live_layout and not quiet:
                            live_layout.update(content)
                
                # Avoid tight loop
                if not line and not err_line:
                    time.sleep(0.01)
                
                # Clear buffer to prevent memory issues
                if len(streaming_buffer) > 100:
                    streaming_buffer = streaming_buffer[-20:]
            
            # Wait for process to complete
            process.wait()
            execution_time = time.time() - start_time
            exit_code = process.returncode
            
            if exit_code == 0:
                logger.success(f"Claude completed successfully in {execution_time:.2f} seconds")
            else:
                logger.error(f"Claude process failed with exit code {exit_code}")
                if result_path.exists() and result_path.stat().st_size > 0:
                    with open(result_path, 'r') as f:
                        result_content = f.read(500)
                        if "usage limit reached" in result_content.lower():
                            logger.error("CLAUDE USAGE LIMIT REACHED - Your account has reached its quota")
                if error_path.exists() and error_path.stat().st_size > 0:
                    with open(error_path, 'r') as f:
                        error_content = f.read(500)
                        logger.error(f"Error output: {error_content}")
            
            result.update({
                "exit_code": exit_code,
                "execution_time": execution_time,
                "success": exit_code == 0,
                "status": "completed" if exit_code == 0 else "failed",
                "result_size": result_path.stat().st_size if result_path.exists() else 0
            })
    
    except Exception as e:
        logger.exception(f"Error streaming Claude output: {e}")
        execution_time = time.time() - start_time if 'start_time' in locals() else 0
        if 'process' in locals() and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        with open(result_path, 'a', encoding='utf-8') as f:
            f.write(f"\n\n[ERROR: {str(e)}]")
        with open(error_path, 'a', encoding='utf-8') as f:
            f.write(str(e) + "\n")
        result.update({
            "execution_time": execution_time,
            "success": False,
            "status": "error",
            "error": str(e),
            "result_size": result_path.stat().st_size if result_path.exists() else 0
        })
    
    return result


def clear_claude_context(claude_path: Optional[str] = None) -> bool:
    """
    Clear Claude's context using the /clear command.
    
    Args:
        claude_path: Path to Claude executable (found automatically if None)
        
    Returns:
        bool: True if clearing was successful, False otherwise
    """
    if claude_path is None:
        claude_path = find_claude_path()
    
    logger.info("Clearing Claude context...")
    
    try:
        process = subprocess.run(
            [claude_path, "/clear"],
            input="\n",
            capture_output=True,
            text=True,
            timeout=10
        )
        if process.returncode == 0:
            logger.info("Claude context cleared successfully")
            return True
        else:
            logger.warning(f"Context clearing failed: {process.stderr[:500]}")
            return False
    except Exception as e:
        logger.error(f"Error clearing context: {e}")
        return False


def run_claude_tasks(
    task_files: List[str],
    clear_context: bool = True,
    claude_path: Optional[str] = None,
    cmd_args: Optional[List[str]] = None,
    timeout_seconds: int = 300
) -> Dict[str, Any]:
    """
    Run multiple Claude tasks in sequence with streaming output.
    
    Args:
        task_files: List of task file paths
        clear_context: Whether to clear context between tasks
        claude_path: Path to Claude executable (found automatically if None)
        cmd_args: Additional command arguments for Claude
        timeout_seconds: Maximum execution time per task in seconds
        
    Returns:
        Dictionary with execution results for all tasks
    """
    if not task_files:
        logger.warning("No task files provided")
        return {"success": False, "error": "No task files provided"}
    
    # Find Claude executable if not provided
    if claude_path is None:
        claude_path = find_claude_path()
    
    logger.info(f"Using Claude at: {claude_path}")
    
    # Initialize command args
    if cmd_args is None:
        cmd_args = []
    
    results = []
    total_start_time = time.time()
    
    for i, task_file in enumerate(task_files):
        if not os.path.exists(task_file):
            logger.error(f"Task file not found: {task_file}")
            results.append({
                "task_file": task_file,
                "success": False,
                "error": "File not found"
            })
            continue
        
        # Run the task with streaming output
        logger.info(f"Running task {i+1}/{len(task_files)}: {task_file}")
        task_result = stream_claude_output(
            task_file=task_file,
            claude_path=claude_path,
            cmd_args=cmd_args,
            timeout_seconds=timeout_seconds
        )
        results.append(task_result)
        
        # Clear context if this isn't the last task
        if clear_context and i < len(task_files) - 1:
            clear_claude_context(claude_path)
    
    total_time = time.time() - total_start_time
    
    # Calculate summary
    successful = sum(1 for r in results if r.get("success", False))
    
    logger.info("=" * 50)
    logger.info("EXECUTION SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Total tasks: {len(task_files)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {len(task_files) - successful}")
    logger.info(f"Total time: {total_time:.2f} seconds")
    logger.info(f"Average time per task: {total_time/max(1, len(task_files)):.2f} seconds")
    
    return {
        "results": results,
        "total_time": total_time,
        "total_tasks": len(task_files),
        "successful_tasks": successful,
        "failed_tasks": len(task_files) - successful
    }


if __name__ == "__main__":
    """
    Validate the claude_streamer module functionality with real test cases.
    """
    import sys
    import argparse
    import tempfile
    
    # Configure logger for validation
    logger.remove()
    logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>")
    
    # List to track all validation failures
    all_validation_failures = []
    total_tests = 0
    
    # Setup validation arguments
    parser = argparse.ArgumentParser(description="Claude Streamer Validation")
    parser.add_argument("--task", help="Optional task file path for direct testing")
    parser.add_argument("--demo", action="store_true", help="Use demo mode with simulated tasks")
    args = parser.parse_args()
    
    # Create a temporary directory for tests
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        logger.info(f"Created temporary directory for tests: {temp_path}")
        
        # Test 1: find_claude_path function
        total_tests += 1
        try:
            claude_path = find_claude_path()
            logger.info(f"Claude path found: {claude_path}")
            
            if not claude_path:
                all_validation_failures.append("find_claude_path test: Returned empty path")
        except Exception as e:
            all_validation_failures.append(f"find_claude_path test error: {str(e)}")
        
        # Test 2: Create a test task file
        total_tests += 1
        test_task_file = str(temp_path / "test_task.md")
        try:
            with open(test_task_file, "w") as f:
                f.write("# Test Task\n\nThis is a test task for validation.\n")
            
            if not os.path.exists(test_task_file):
                all_validation_failures.append("File creation test: Failed to create test task file")
        except Exception as e:
            all_validation_failures.append(f"File creation test error: {str(e)}")
        
        # Test 3: Validate function parameters and return values
        total_tests += 1
        try:
            test_script_path = str(temp_path / "test_echo.sh")
            with open(test_script_path, "w") as f:
                f.write("#!/bin/bash\n")
                f.write("cat > /dev/null\n")
                f.write("echo 'Task completed successfully'\n")
                f.write("echo 'Content from task file was processed'\n")
            
            os.chmod(test_script_path, 0o755)
            
            cmd_args_test = ["--arg1", "--arg2=value"]
            test_args_str = stream_claude_output(
                task_file=test_task_file,
                claude_path=test_script_path,
                cmd_args=cmd_args_test,
                timeout_seconds=1
            )
            
            required_keys = ["task_file", "result_file", "error_file", "exit_code", 
                           "execution_time", "success"]
            missing_keys = [key for key in required_keys if key not in test_args_str]
            if missing_keys:
                all_validation_failures.append(f"Parameter validation test: Missing keys in result: {missing_keys}")
        except Exception as e:
            all_validation_failures.append(f"Parameter validation test error: {str(e)}")
        
        # Test 4: Test response to timeout
        total_tests += 1
        try:
            slow_script_path = str(temp_path / "slow_script.sh")
            with open(slow_script_path, "w") as f:
                f.write("#!/bin/bash\n")
                f.write("cat > /dev/null\n")
                f.write("echo 'Starting slow operation...'\n")
                f.write("sleep 3\n")
                f.write("echo 'This should not be reached due to timeout'\n")
            
            os.chmod(slow_script_path, 0o755)
            
            timeout_result = stream_claude_output(
                task_file=test_task_file,
                claude_path=slow_script_path,
                timeout_seconds=1
            )
            
            if timeout_result.get("status") != "timeout":
                all_validation_failures.append(f"Timeout test: Expected status 'timeout', got '{timeout_result.get('status')}'")
            
            result_file = timeout_result.get("result_file")
            if result_file and os.path.exists(result_file):
                with open(result_file, "r") as f:
                    content = f.read()
                    if "TIMEOUT" not in content:
                        all_validation_failures.append(f"Timeout test: Expected timeout message in result file")
        except Exception as e:
            all_validation_failures.append(f"Timeout test error: {str(e)}")
        
        # Test 5: clear_claude_context
        total_tests += 1
        try:
            result = clear_claude_context("/bin/echo")
            if result is not True and result is not False:
                all_validation_failures.append(f"clear_claude_context test: Expected boolean result, got {type(result)}")
            logger.info(f"Context clearing test completed")
        except Exception as e:
            all_validation_failures.append(f"clear_claude_context test error: {str(e)}")
        
        # Test 6: run_claude_tasks with multiple tasks
        total_tests += 1
        try:
            test_task_file2 = str(temp_path / "test_task2.md")
            with open(test_task_file2, "w") as f:
                f.write("# Test Task 2\n\nThis is another test task for validation.\n")
            
            result = run_claude_tasks(
                task_files=[test_task_file, test_task_file2],
                claude_path="/bin/echo",
                timeout_seconds=1
            )
            
            required_keys = ["results", "total_time", "total_tasks", 
                            "successful_tasks", "failed_tasks"]
            missing_keys = [key for key in required_keys if key not in result]
            if missing_keys:
                all_validation_failures.append(f"run_claude_tasks test: Missing keys in result: {missing_keys}")
            
            if result.get("total_tasks") != 2:
                all_validation_failures.append(f"run_claude_tasks test: Expected 2 total tasks, got {result.get('total_tasks')}")
            
            if result.get("successful_tasks", 0) < 1:
                all_validation_failures.append(f"run_claude_tasks test: Expected at least 1 successful task")
        except Exception as e:
            all_validation_failures.append(f"run_claude_tasks test error: {str(e)}")
    
    # Final validation result
    if all_validation_failures:
        print(f"\n❌ VALIDATION FAILED - {len(all_validation_failures)} of {total_tests} tests failed:")
        for failure in all_validation_failures:
            print(f"  - {failure}")
        sys.exit(1)
    else:
        print(f"\n✅ VALIDATION PASSED - All {total_tests} tests produced expected results")
        sys.exit(0)
