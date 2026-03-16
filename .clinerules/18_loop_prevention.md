# Loop Prevention Rules

The AI must not repeatedly modify the same file without changing strategy.

If the same file has been modified 2 times consecutively:

The AI must:

1. stop editing that file
2. inspect other modules
3. analyze root cause

Never edit the same file more than 3 times in a row.