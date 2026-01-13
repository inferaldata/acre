# Acre Demo Recording

Scripts for recording promotional demos of acre using VHS.

## Prerequisites

```bash
# Install VHS
brew install vhs
# or
go install github.com/charmbracelet/vhs@latest

# Ensure these are globally available
which zellij claude acre
```

## Recording

1. Copy the layout file to your home directory (or adjust path in tape):
   ```bash
   cp acre-demo.kdl ~/demos/
   ```

2. Run the VHS script:
   ```bash
   vhs acre-demo.tape
   ```

3. The script will:
   - Clone ripgrep to /tmp (hidden from recording)
   - Start zellij with two tabs
   - Launch Claude and send a prompt
   - Switch to acre to review changes
   - Iterate with Claude

## Post-processing

Speed up the long waits and create GIF:

```bash
# Speed up 2x
ffmpeg -i acre-demo.mp4 -filter:v "setpts=0.5*PTS" acre-demo-fast.mp4

# Create GIF (smaller, for README)
ffmpeg -i acre-demo-fast.mp4 -vf "fps=10,scale=960:-1:flags=lanczos" acre-demo.gif
```

## Tips

- **Claude timing is unpredictable** - you may need to adjust Sleep values or do multiple takes
- **Alt+1/Alt+2** switches zellij tabs - adjust if you have different keybindings
- **Review the raw recording** before post-processing to check timing
- For best results, **manually control Claude** while recording and adjust the script timing afterwards

## Files

| File | Purpose |
|------|---------|
| `acre-demo.tape` | VHS recording script |
| `acre-demo.kdl` | Zellij layout (two tabs) |
