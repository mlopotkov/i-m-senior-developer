---
type: regex
name: takes-the-seam-from-the-detected-stack
target: { source: file, path: features/FEAT-0001-turn-timer/ARCH-01.md }
pattern: '(?=[\s\S]*Phaser)(?=[\s\S]*(?:no specific reference|no matching reference|reference gap|нет[^\n]{0,80}справочник|отсутствует[^\n]{0,80}reference))(?=[\s\S]*(?:TurnScene|scene|сцена|src/|module|модуль))'
flags: i
match: contains
---
