# Fixed Dashboard for Claude Task Runner

The fixed dashboard feature provides a truly fixed dashboard UI that remains at the top of the terminal while Claude output scrolls below it. This solves the issue where the dashboard scrolls out of view during task execution.

## Key Features

1. **Fixed Status Area**: The dashboard remains fixed at the top of the terminal, showing task status at all times
2. **Scrolling Content Area**: Claude's output appears in a scrolling area below the fixed dashboard
3. **Real-time Updates**: Task status and Claude output are updated in real time
4. **Terminal Resizing Support**: The UI handles terminal resizing gracefully

## Usage

The fixed dashboard is enabled by default when running the task runner:

```bash
python -m task_runner run input/sample_tasks.md --base-dir ./debug_project
```

If you prefer not to use the fixed dashboard, you can disable it with:

```bash
python -m task_runner run input/sample_tasks.md --base-dir ./debug_project --no-fixed-dashboard
```

Or use the convenience script:

```bash
./run_fixed_dashboard.sh
```

## Implementation Details

The fixed dashboard implementation uses Rich's `Layout` and `Live` components together in the correct way to maintain a fixed UI. The key improvements include:

1. **Proper Layout Management**: Using split layouts with fixed and flexible sections
2. **Screen Clearing**: Ensuring clean display with proper screen clearing
3. **Content Scrolling**: Implementing expand=True for proper content scrolling within panels
4. **Update Management**: Managing display updates efficiently to prevent flickering

## Architecture

The implementation consists of:

- `fixed_position_dashboard.py`: The core dashboard implementation
- `run_with_fixed_dashboard.py`: Entry point for running tasks with the fixed dashboard
- Integration with claude_streamer.py for real-time streaming updates

## Comparison with Previous Approaches

Previous dashboard implementations had these issues:
- The dashboard would scroll out of view when new Claude data arrived
- The screen would not clear properly, leading to visual artifacts
- The output would not scroll properly within panels

The new implementation fixes all these issues, providing a smooth, fixed UI experience.