---
title: "Making External Script Logs Observable in UiPath RPA"
subtitle: "How I helped a customer bring Python and application logs back into the UiPath execution trail"
tags: uipath, rpa, observability, python, automation
---

# Making External Script Logs Observable in UiPath RPA

In many RPA projects, UiPath is not the only thing doing the work.

Sometimes the robot needs to call a Python script, a batch file, a command-line utility, or another external application because that component already exists, solves a niche problem well, or is owned by another team.

That is perfectly reasonable from an automation design point of view. But it creates one uncomfortable operational question:

> What happens to observability when the real work moves outside the UiPath workflow?

I worked on a customer project where this exact problem came up. The UiPath process launched an external Python script, but the script's runtime details were not naturally visible in the UiPath job logs. If the script ran for a long time, slowed down, failed silently, or got stuck between steps, the support team had limited visibility from the UiPath side.

The goal was simple: when an external script or application is called from a UiPath RPA process, its logs should still show up as part of the robot execution trail.

## The Problem

UiPath gives us strong logging inside the workflow through Log Message activities and Orchestrator job logs. But once a robot starts an external process, that process has its own runtime.

For example:

- A Python script may write to a local text file.
- A command-line utility may print to the console.
- A legacy application may create its own diagnostic log.
- A batch file may run for hours without returning control to the robot.

From the robot's perspective, the external process may look like a single activity: "start process". But from the operations team's perspective, that is not enough.

They need to know:

- Is the script still running?
- What step is it currently on?
- Did it emit a warning or error?
- Can we see the script messages in the same place as the UiPath job logs?
- Can we avoid mixing old log entries from previous runs into the current job?

This last point is especially important. If an external script keeps appending to the same log file, the robot must not replay historical entries every time it runs.

## The Design

The solution I built used a simple log-bridging pattern:

1. The external Python script writes structured log records to a runtime log file.
2. UiPath starts the script through a batch file using `cmd.exe`.
3. Before starting the script, UiPath records the current number of lines in the log file.
4. While the script is running, UiPath polls the log file for newly appended lines.
5. Each new log record is parsed with UiPath JSON activities.
6. The parsed message is written into the UiPath workflow log using the matching log level.
7. When the external process exits, UiPath performs one final scan to capture any last log lines.

The result is that logs generated outside UiPath become visible inside the UiPath execution context.

## The Project Structure

The project was intentionally small and focused:

```text
AddPythonCustomLogs
├── Main.xaml
├── Parallel logging till scipt executes.xaml
├── MonitorNewLogLines.xaml
└── Python scripts
    ├── RunLogger.bat
    ├── Logger.py
    └── test_logger.py
```

`runtime_log.txt` is created by the Python script at runtime.

The UiPath side has three workflows:

- `Main.xaml` starts the external script and initializes the log cursor.
- `Parallel logging till scipt executes.xaml` watches the command prompt window while polling logs.
- `MonitorNewLogLines.xaml` reads only new log records and writes them into UiPath logs.

The Python side has:

- `Logger.py`, which writes structured runtime messages.
- `RunLogger.bat`, which launches the Python script from the correct folder.
- `test_logger.py`, which validates the logging contract.

## The Logging Contract

The first important decision was to make the external script emit structured logs instead of plain text.

Each Python log line is written as a JSON object:

```json
{"timestamp":"2026-05-26T12:00:00+00:00","loglevel":"Error","message":"Script is running"}
```

The current sample defaults to `Error` so it is easy to confirm that the external severity is preserved when it reaches UiPath.

This gives UiPath a predictable contract:

- `timestamp` tells us when the external script created the record.
- `loglevel` tells us how the message should be mapped in UiPath.
- `message` is the text that should appear in the UiPath job log.

The current UiPath workflow uses `loglevel` and `message`. The timestamp remains available in the source log file if the pattern is extended later.

That structure matters. Without it, the robot would need to guess whether a line is informational, a warning, or an error.

## Starting the External Script

The batch file is deliberately minimal:

```bat
@echo off
cd /d "%~dp0"
python "%~dp0Logger.py"
```

This does two useful things:

- It makes the script run from its own folder.
- It keeps path handling simple, even when UiPath launches the batch file from another working directory.

In `Main.xaml`, UiPath starts `cmd.exe` with this argument:

```text
/c "<batFilePath>"
```

It also sets the working directory to:

```text
Path.GetDirectoryName(batFilePath)
```

Before starting the external process, the workflow checks whether the runtime log already exists and stores the existing line count in a variable called `lineCursor`.

Conceptually:

```text
if runtime_log.txt exists:
    lineCursor = current number of lines
else:
    lineCursor = 0

start cmd.exe /c RunLogger.bat
start monitoring newly appended log lines
```

This small cursor is what prevents old logs from being replayed into the new robot run.

## Monitoring While the Script Runs

The monitoring workflow uses a parallel pattern.

One branch checks whether the command prompt window is still visible. The other branch periodically calls `MonitorNewLogLines.xaml` to read newly appended log records.

In the latest project code, the monitor uses:

- A UiPath UI Automation `NCheckState` activity to detect the Windows Terminal command prompt window.
- A 5-second delay before the first command prompt state check.
- A 2-minute delay between subsequent command prompt state checks.
- A 5-second log polling delay while the script is running.

When the command prompt is no longer visible, the parallel section ends. Then UiPath invokes the log reader one final time.

That final scan is important because an external process may write its last few log lines right before closing. Without a final read, those messages could be missed.

## Reading Only New Log Lines

`MonitorNewLogLines.xaml` is the reusable part of the solution.

It accepts:

- `logFilePath` as an input argument.
- `lineCursor` as an input/output argument.

The workflow reads the current file snapshot, skips every line that was already processed, and handles only the new lines:

```text
logLines = read all lines from runtime_log.txt

if logLines.Length < lineCursor:
    lineCursor = 0

for each line in logLines.Skip(lineCursor):
    reset parsed values
    deserialize JSON into JObject
    validate loglevel and message
    normalize log level
    write UiPath log message

lineCursor = logLines.Length
```

There is also a useful edge-case guard here: if the file becomes shorter than the cursor, the workflow assumes the log was truncated or rotated and resets the cursor.

## Parsing JSON with UiPath Activities

An important update in the latest version is that JSON parsing is handled with UiPath activities instead of custom inline parsing code.

`MonitorNewLogLines.xaml` uses:

- `DeserializeJson` from `UiPath.WebAPI.Activities`.
- `Newtonsoft.Json.Linq.JObject` to inspect the parsed record.
- A `TryCatch` around deserialization so malformed lines do not crash the monitor.
- A validation step that requires `loglevel` and `message` to exist and be string values.

If a record is malformed, incomplete, or uses an unsupported level, the workflow writes a UiPath error log containing the raw line. That way bad telemetry is visible instead of silently disappearing.

## Mapping External Log Levels to UiPath Log Levels

The workflow parses each JSON line and maps the external `loglevel` value to a UiPath Log Message level:

| External level | UiPath level |
|---|---|
| `TRACE` | `Trace` |
| `INFO`, `INFORMATION` | `Info` |
| `WARN`, `WARNING` | `Warn` |
| `ERROR` | `Error` |
| `FATAL` | `Fatal` |

This keeps the original severity signal from the external process intact when the message reaches the UiPath job log.

## Why This Helped the Customer

The value of this solution was not that it introduced a complex logging platform. It was valuable because it made an existing automation easier to operate.

After this pattern was added:

- The UiPath job log showed what the external script was doing.
- Support teams did not need to separately inspect the script folder for basic diagnostics.
- Warnings and errors from the script became visible in the robot's execution trail.
- Historical logs were not duplicated on each run.
- Long-running script activity became easier to track.
- Invalid external log records became visible as UiPath errors instead of being ignored.
- The pattern could be reused for other external applications, not just Python.

This is the kind of improvement that may look small in code but has a big impact in production support.

## Lessons Learned

The main lesson was that external execution should not mean external observability.

If a robot calls something outside UiPath, we should decide how that external component will communicate status back to the automation platform.

For this project, a file-based bridge was enough. In a larger system, the same idea could be implemented with a queue, API endpoint, telemetry collector, or centralized logging platform. But the core pattern stays the same:

> Give the external process a structured logging contract, then bridge those logs back into the RPA execution context.

A few design choices made the solution more reliable:

- Use structured JSON logs instead of free-form text.
- Track a cursor so only new records are processed.
- Preserve the original log severity.
- Parse JSON with platform activities where possible.
- Handle invalid records explicitly.
- Perform a final scan after the external process exits.
- Keep the external launcher simple and predictable.

## Where This Pattern Fits

This pattern is useful when a UiPath workflow needs to call:

- Python scripts
- PowerShell scripts
- Batch files
- Console applications
- Legacy tools
- Vendor command-line utilities
- Long-running helper applications

It is especially useful when the external process has meaningful internal progress that the robot operator should be able to see.

## Final Thoughts

Observability is not only about collecting logs. It is about making sure the right person can understand what happened without hunting across machines, folders, and tools.

In this customer project, the challenge was that part of the automation lived outside UiPath. By introducing a structured log file, a cursor-based reader, and a UiPath workflow that replayed only new records into the robot log, we made that external work visible again.

The result was a more supportable automation: same external script, same UiPath process, but a much clearer runtime story.

That is often where good automation engineering shows up: not just in making the process run, but in making it understandable when someone needs to support it later.
