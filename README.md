# Mpv controller
Control your mpv from ulauncher

## Dependencies:
1. [mpv video player](https://mpv.io): self explanatory
2. [fzf](https://github.com/junegunn/fzf): to have fuzzy finding when selecting options

You must have both binaries in your path for this to work.

## Notes
Copy this text to your .config/mpv/mpv.conf, it this file doesn't exist create it
```
input-ipc-server=~~/socket
```
This is necessary for this extension to work, since creates a unix socket that allows to communicate with a working mpv instance.

For this same reason it provably doesn't work on Windows or Mac.

