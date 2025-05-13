#!/usr/bin/env python3
"""
Textual Dashboard for Claude Task Runner

This module provides a modern TUI dashboard based on the Textual framework,
featuring task status display and real-time Claude output streaming in a
clean, user-friendly interface.

Links:
- Textual Documentation: https://textual.textualize.io/
- Rich Documentation: https://rich.readthedocs.io/

Sample input:
- Task state dictionary from TaskManager
- Claude streaming output

Sample output:
- Interactive terminal dashboard with real-time updating
"""

import queue
import time
import threading
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from loguru import logger
from textual.app import App
from textual.widgets import (
    Button, Footer, Header, Static,
    DataTable
)
from textual.reactive import reactive
from textual.binding import Binding
from textual import events, containers


class TaskStatusWidget(Static):
    """Widget displaying task status information."""
    
    task_state = reactive({})
    current_task = reactive(None)
    
    def __init__(self, task_state: Dict[str, Dict[str, Any]], current_task: Optional[str] = None):
        """Initialize with task state and current task."""
        super().__init__()
        self.task_state = task_state
        self.current_task = current_task
        logger.debug(f"Initialized TaskStatusWidget with task_state: {task_state}, current_task: {current_task}")
    
    def update_tasks(self, task_state: Dict[str, Dict[str, Any]], current_task: Optional[str] = None):
        """Update the task state and current task."""
        self.task_state = task_state
        if current_task is not None:
            self.current_task = current_task
    
    def watch_task_state(self, task_state: Dict[str, Dict[str, Any]]):
        """React to changes in task state."""
        logger.debug(f"Task state updated: {task_state}")
        self.update_content()
    
    def watch_current_task(self, current_task: Optional[str]):
        """React to changes in current task."""
        logger.debug(f"Current task updated: {current_task}")
        self.update_content()
    
    def update_content(self):
        """Update the displayed content based on current state."""
        from rich.table import Table

        # Create a rich table for task status (not Textual DataTable)
        table = Table()
        table.add_column("Task", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Progress", style="green")
        table.add_column("Time (s)", style="blue") 
        
        # Add tasks to the table
        for task_name, state in sorted(self.task_state.items()):
            status = state.get("status", "unknown")
            execution_time = state.get("execution_time", "")
            
            # Format execution time if present
            if execution_time:
                try:
                    execution_time = f"{float(execution_time):.1f}"
                except (ValueError, TypeError):
                    execution_time = str(execution_time)
            
            # Calculate progress indicator with status-based styling
            if status == "completed":
                progress = "[green]✓ 100%[/green]"
                status_display = f"[green]{status}[/green]"
            elif status == "failed":
                progress = "[red]✗[/red]"
                status_display = f"[red]{status}[/red]"
            elif status == "timeout":
                progress = "[yellow]⏱️ TIMEOUT[/yellow]"
                status_display = f"[yellow]{status}[/yellow]"
            elif status == "running":
                progress = "[blue]⟳ Running...[/blue]"
                status_display = f"[blue]{status}[/blue]"
            else:
                progress = "[white]...[/white]"
                status_display = f"[white]{status}[/white]"
            
            # Highlight current task
            if task_name == self.current_task:
                task_display = f"[bold cyan]➤ {task_name}[/bold cyan]"
            else:
                task_display = task_name
            
            # Add the row
            table.add_row(
                task_display, 
                status_display, 
                progress, 
                execution_time
            )
        
        # Update the content with the rich table
        self.update(table)


class StreamingOutputWidget(Static):
    """Widget displaying real-time streaming output from Claude."""
    
    content = reactive("")
    
    def __init__(self):
        """Initialize an empty streaming widget."""
        super().__init__()
        self.content = ""
        logger.debug("Initialized StreamingOutputWidget")
    
    def update_streaming_content(self, content: str):
        """Update the streaming content."""
        self.content = content
    
    def watch_content(self, content: str):
        """React to changes in streaming content."""
        logger.debug(f"Streaming content updated: {content[:100]}...")
        try:
            # Try to render as markdown for better output formatting
            markdown_content = Markdown(content)
            self.update(markdown_content)
        except Exception as e:
            logger.error(f"Markdown parsing failed: {e}")
            # Fall back to plain text if markdown parsing fails
            self.update(content)
        self.scroll_end()


class ClaudeDashboard(App):
    """Textual dashboard application for Claude Task Runner."""
    
    # Use on_mount instead of CSS since Textual 3.2.0 CSS support is different
    async def on_mount(self):
        """Set up tasks when app is mounted."""
        logger.debug("Mounting ClaudeDashboard")
        # Set up the layout manually instead of CSS for Textual 3.2.0
        # Get dashboard container
        dashboard_container = self.query_one("#dashboard-container")
        
        # Configure layout
        dashboard_container.styles.layout = "vertical"
        dashboard_container.styles.height = "100%"
        dashboard_container.styles.width = "100%"
        
        # Configure task status header
        status_header = self.query_one("#task-status-header")
        status_header.styles.background = "#2a4494"
        status_header.styles.color = "#ffffff"
        status_header.styles.padding = (1, 2)
        status_header.styles.text_align = "center"
        status_header.styles.bold = True
        
        # Configure streaming output header
        output_header = self.query_one("#streaming-output-header")
        output_header.styles.background = "#224870"
        output_header.styles.color = "#ffffff"
        output_header.styles.padding = (1, 2)
        output_header.styles.text_align = "center"
        output_header.styles.bold = True
        
        # Configure task status panel
        status_panel = self.query_one("#task-status")
        status_panel.styles.height = "25%"
        status_panel.styles.border = ("heavy", "#2a4494")
        status_panel.styles.padding = (0, 1)
        status_panel.styles.overflow = "auto"
        
        # Configure streaming output panel
        output_panel = self.query_one("#streaming-output")
        output_panel.styles.height = "75%"
        output_panel.styles.border = ("heavy", "#224870")
        output_panel.styles.padding = (0, 1)
        output_panel.styles.overflow = "auto scroll"
        
        # Initial update
        if self._status_widget:
            self._status_widget.update_tasks(self.task_state, self.current_task)
            logger.debug("Initial task status update performed")
    
    # Keyboard bindings
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]
    
    def __init__(
        self, 
        task_state: Dict[str, Dict[str, Any]] = None, 
        current_task: Optional[str] = None,
        update_callback: Optional[Callable] = None
    ):
        """
        Initialize the dashboard with task state.
        
        Args:
            task_state: Dictionary of task states
            current_task: Name of the currently running task
            update_callback: Function to call when UI state updates
        """
        super().__init__()
        self.task_state = task_state or {}
        self.current_task = current_task
        self.update_callback = update_callback
        self._streaming_widget = None
        self._status_widget = None
        logger.debug("Initialized ClaudeDashboard")
    
    def compose(self):
        """Build the dashboard UI."""
        logger.debug("Composing dashboard UI")
        # Create components directly - simpler approach for Textual 3.2.0
        
        # Header and footer
        yield Header()
        
        # Create container and all components
        dashboard_container = containers.Container(id="dashboard-container")
        
        # Status header and panel
        status_header = Static("Task Status", id="task-status-header")
        self._status_widget = TaskStatusWidget(self.task_state, self.current_task)
        self._status_widget.id = "task-status"
        
        # Output header and panel
        output_header = Static("Claude Output", id="streaming-output-header")
        self._streaming_widget = StreamingOutputWidget()
        self._streaming_widget.id = "streaming-output"
        
        # Mount components to container in the desired order
        dashboard_container.mount(status_header)
        dashboard_container.mount(self._status_widget)
        dashboard_container.mount(output_header)
        dashboard_container.mount(self._streaming_widget)
        
        # Yield the container with all components mounted
        yield dashboard_container
        
        # Footer
        yield Footer()
        logger.debug("Completed dashboard UI composition")
    
    def update_streaming_content(self, content: str):
        """
        Update the streaming content area with new content.
        
        Args:
            content: New content to display
        """
        if self._streaming_widget:
            self._streaming_widget.update_streaming_content(content)
            logger.debug("Updated streaming content in UI")
    
    def update_task_state(self, task_state: Dict[str, Dict[str, Any]], current_task: Optional[str] = None):
        """
        Update the task state in the dashboard.
        
        Args:
            task_state: Dictionary of task states
            current_task: Name of the currently running task
        """
        self.task_state = task_state
        if current_task is not None:
            self.current_task = current_task
            
        if self._status_widget:
            self._status_widget.update_tasks(task_state, current_task)
            logger.debug("Updated task state in UI")


class TextualDashboardRunner:
    """Helper class to run the Textual dashboard with proper integration."""
    
    def __init__(self, initial_task_state: Dict[str, Dict[str, Any]] = None):
        """Initialize with initial task state."""
        self.dashboard = ClaudeDashboard(task_state=initial_task_state or {})
        self._update_queue = queue.Queue()
        self._content_queue = queue.Queue()
        self._stop_event = threading.Event()
        logger.debug("Initialized TextualDashboardRunner")
    
    def update_streaming_content(self, content: str):
        """
        Update streaming content in the dashboard.
        This method is called from outside the Textual app.
        
        Args:
            content: New content to display
        """
        try:
            self._content_queue.put_nowait(content)
            logger.debug(f"Queued streaming content: {content[:100]}...")
        except Exception as e:
            logger.error(f"Error queuing content update: {e}")
    
    def update_task_state(self, task_state: Dict[str, Dict[str, Any]], current_task: Optional[str] = None):
        """
        Update task state in the dashboard.
        This method is called from outside the Textual app.
        
        Args:
            task_state: New task state dictionary
            current_task: New current task
        """
        try:
            self._update_queue.put_nowait((task_state, current_task))
            logger.debug(f"Queued task state: {task_state}, current_task: {current_task}")
        except Exception as e:
            logger.error(f"Error queuing task state update: {e}")
    
    async def _process_queues(self):
        """Process updates from queues within Textual's event loop."""
        logger.debug("Processing queues")
        while not self._stop_event.is_set():
            try:
                while not self._content_queue.empty():
                    content = self._content_queue.get_nowait()
                    self.dashboard.update_streaming_content(content)
                    self._content_queue.task_done()
                    logger.debug("Processed content queue update")
            except Exception as e:
                logger.error(f"Error processing content update: {e}")
            
            try:
                while not self._update_queue.empty():
                    task_state, current_task = self._update_queue.get_nowait()
                    self.dashboard.update_task_state(task_state, current_task)
                    self._update_queue.task_done()
                    logger.debug("Processed task state queue update")
            except Exception as e:
                logger.error(f"Error processing task state update: {e}")
            
            await asyncio.sleep(0.1)
    
    async def run(self):
        """Run the dashboard application."""
        logger.debug("Starting Textual dashboard run")
        # Start queue processing
        self.dashboard.set_interval(0.1, self._process_queues)
        try:
            await self.dashboard.run_async()
            logger.debug("Textual dashboard run completed")
        except Exception as e:
            logger.error(f"Error running Textual dashboard: {e}")
        finally:
            self._stop_event.set()
            logger.debug("Textual dashboard stopped")


def run_with_textual_dashboard(task_state: Dict[str, Dict[str, Any]], update_handler_callback: Callable):
    """
    Run a Textual dashboard with the given task state and update handler.
    
    Args:
        task_state: Initial task state dictionary
        update_handler_callback: Function to call with dashboard handlers
            The callback receives:
                - streaming_update_handler: Function to update streaming content
                - task_state_update_handler: Function to update task state
    
    Returns:
        Dashboard runner instance
    """
    logger.debug("Launching Textual dashboard")
    # Create dashboard runner
    runner = TextualDashboardRunner(initial_task_state=task_state)
    
    # Call the update handler callback with the update functions
    try:
        if update_handler_callback:
            logger.debug("Setting up update handlers")
            update_handler_callback(
                streaming_update_handler=runner.update_streaming_content,
                task_state_update_handler=runner.update_task_state
            )
    except Exception as e:
        logger.error(f"Error setting up update handlers: {e}")
    
    # Run the dashboard
    asyncio.run(runner.run())
    
    return runner


# Entry point for standalone testing
def run_textual_dashboard():
    """Run the Textual dashboard in standalone mode for testing."""
    logger.debug("Running Textual dashboard in standalone mode")
    # Create sample task state
    sample_tasks = {
        "001_analyze_code.md": {"status": "completed", "execution_time": 45.2},
        "002_generate_docs.md": {"status": "running", "execution_time": 12.8},
        "003_write_tests.md": {"status": "pending"},
        "004_refactor_core.md": {"status": "failed", "execution_time": 23.1},
    }
    
    # Sample update function for testing
    def demo_updater(streaming_update_handler, task_state_update_handler):
        import threading
        import time
        
        def update_demo_content():
            content = "# Claude Output\n\n"
            for i in range(10):
                content += f"This is line {i+1} of simulated Claude output.\n"
                streaming_update_handler(content)
                task_state_update_handler(sample_tasks, "002_generate_docs.md")
                time.sleep(0.5)
        
        # Start demo thread
        threading.Thread(target=update_demo_content, daemon=True).start()
    
    # Run the dashboard with the sample state
    run_with_textual_dashboard(sample_tasks, demo_updater)


if __name__ == "__main__":
    """Validate the textual dashboard."""
    import sys
    
    # Configure logger for validation
    logger.remove()
    logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>")
    
    # List to track all validation failures
    all_validation_failures = []
    total_tests = 0
    
    try:
        # Test 1: Create dashboard runner
        total_tests += 1
        try:
            runner = TextualDashboardRunner()
            if not runner:
                all_validation_failures.append("Dashboard runner creation failed")
        except Exception as e:
            all_validation_failures.append(f"Dashboard runner creation error: {e}")
        
        # Test 2: Create ClaudeDashboard
        total_tests += 1
        try:
            sample_tasks = {
                "001_test_task.md": {"status": "completed", "execution_time": 5.0}
            }
            dashboard = ClaudeDashboard(task_state=sample_tasks, current_task="001_test_task.md")
            if not dashboard:
                all_validation_failures.append("ClaudeDashboard creation failed")
        except Exception as e:
            all_validation_failures.append(f"ClaudeDashboard creation error: {e}")
        
        # Test 3: Create TaskStatusWidget
        total_tests += 1
        try:
            widget = TaskStatusWidget(sample_tasks, "001_test_task.md")
            if not widget:
                all_validation_failures.append("TaskStatusWidget creation failed")
        except Exception as e:
            all_validation_failures.append(f"TaskStatusWidget creation error: {e}")
            
        # Test 4: Create StreamingOutputWidget
        total_tests += 1
        try:
            widget = StreamingOutputWidget()
            widget.update_streaming_content("Test content")
            if widget.content != "Test content":
                all_validation_failures.append("StreamingOutputWidget content update failed")
        except Exception as e:
            all_validation_failures.append(f"StreamingOutputWidget creation/update error: {e}")
    
        # Final validation result
        if all_validation_failures:
            print(f"\n❌ VALIDATION FAILED - {len(all_validation_failures)} of {total_tests} tests failed:")
            for failure in all_validation_failures:
                print(f"  - {failure}")
            sys.exit(1)  # Exit with error code
        else:
            print(f"\n✅ VALIDATION PASSED - All {total_tests} tests produced expected results")
            print("Function is validated and formal tests can now be written")
            
            # Ask if user wants to run the demo
            print("\nDo you want to run the Textual dashboard demo? (y/n)")
            choice = input().strip().lower()
            if choice in ('y', 'yes'):
                run_textual_dashboard()
                
            sys.exit(0)  # Exit with success code
    except Exception as e:
        print(f"Unexpected error during validation: {e}")
        sys.exit(1)