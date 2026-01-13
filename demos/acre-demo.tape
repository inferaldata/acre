# acre-demo.tape
# VHS script for recording acre + Claude workflow demo
#
# Run: vhs acre-demo.tape
# Requires: vhs, zellij, claude, acre (globally installed)

Output acre-demo.mp4
Set FontSize 20
Set Width 1920
Set Height 1080
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set Padding 20

# Hidden setup - create a tiny project
Hide
Type "export DEMO_DIR=$PWD"
Enter
Sleep 200ms
Type "cd /tmp && rm -rf acre-demo && mkdir -p acre-demo/mylib && cd acre-demo/mylib"
Enter
Sleep 500ms
Type "git init"
Enter
Sleep 500ms
# Copy the sample Python file
Type "cp $DEMO_DIR/calculator.py ."
Enter
Sleep 300ms
Type "git add -A && git commit -m 'Initial commit'"
Enter
Sleep 500ms
# Create Claude settings - sonnet model
Type `mkdir -p .claude && echo '{"model": "sonnet"}' > .claude/settings.json`
Enter
Sleep 300ms
Type "clear"
Enter
Sleep 300ms
Show

# Start zellij with tabs layout in a new session
Type "zellij --new-session-with-layout $DEMO_DIR/acre-demo.kdl"
Enter
Sleep 2s

# Tab 1 (claude) is active - start claude with permissions bypassed
Type "claude --dangerously-skip-permissions"
Enter
Sleep 3s

# Send prompt to Claude - add multiply with docstring
Type "Add a multiply function with a docstring. Be concise."
Enter

# Wait for Claude to finish (will be sped up in post-processing)
Sleep 30s

# Switch to Tab 2 (acre) using Ctrl+B
Ctrl+B
Sleep 1s

# Start acre to review the changes (full screen now!)
Type "acre"
Enter
Sleep 2s

# Navigate through the diff
Type "j"
Sleep 300ms
Type "j"
Sleep 300ms
Type "j"
Sleep 1s

# Mark as reviewed
Type "r"
Sleep 500ms

# Add a review comment asking about the implementation
Type "c"
Sleep 500ms
Type "Add a divide function with proper division by zero handling."
Sleep 1s
# Press Ctrl+S to submit (zellij keybinds cleared)
Ctrl+S
Sleep 2s

# Switch back to Claude (Tab 1) using Ctrl+A
Ctrl+A
Sleep 500ms

# Tell Claude to read the review and respond
Type "Check .acre-review.yaml for review comments and respond to them."
Enter

# Wait for Claude to read and respond
Sleep 30s

# Back to acre (Tab 2) to see Claude's response (hot-reloads automatically)
Ctrl+B
Sleep 2s

# Navigate to see the comment with response
Type "j"
Sleep 500ms
Type "j"
Sleep 500ms

# Wrap up - show the collaboration
Sleep 3s
