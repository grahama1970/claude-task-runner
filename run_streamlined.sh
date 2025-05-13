#!/bin/bash
# Run script to test the streamlined UI that shows the dashboard only once at the beginning
# This script creates sample tasks and runs them with a single dashboard display

# Ensure we're running from the project root
cd "$(dirname "$0")" || exit 1

# Create sample directories
mkdir -p streamlined_demo/tasks
mkdir -p streamlined_demo/results

# Create sample tasks
cat << EOF > streamlined_demo/tasks/001_first_task.md
# First Task

Please introduce yourself and explain what capabilities you have.
EOF

cat << EOF > streamlined_demo/tasks/002_second_task.md
# Second Task

Please calculate the following:
1. 123 + 456
2. 789 * 321
3. The square root of 144
EOF

echo "Created sample tasks in streamlined_demo/tasks/"

# Run the task runner with streamlined UI
echo "Running the task runner with streamlined UI (display table only once)..."
python -m task_runner.cli.app run --base-dir ./streamlined_demo --no-table-repeat

echo "Done! Check streamlined_demo/results for output."