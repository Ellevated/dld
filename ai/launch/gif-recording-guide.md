# GIF Recording Guide

## Setup
- Terminal: Dark theme, large font (16px+)
- Resolution: 1280x720
- Tool: Kap (macOS), OBS (cross-platform), asciinema

## Scene 1: Project Creation (10s)
```
npx create-dld demo-project
cd demo-project
```

## Scene 2: Bootstrap (20s)
```
claude
> /bootstrap
```
Show: Answering 2-3 questions, idea extraction

## Scene 3: Spark (20s)
```
> /spark add user authentication
```
Show: Research happening, spec being created

## Scene 4: Autopilot (20s)
```
> /autopilot
```
Show: Tasks executing, commits appearing

## Scene 5: Result (10s)
```
git log --oneline
```
Show: Clean commit history

## Total: ~80 seconds

## Post-Processing
1. Speed up waiting parts 2x
2. Add captions at key moments
3. Convert to GIF: `ffmpeg -i demo.mp4 -vf "fps=10,scale=1280:-1" demo.gif`
4. Optimize: `gifsicle -O3 demo.gif -o workflow.gif`
5. Target size: <5MB for GitHub
