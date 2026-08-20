Absorb knowledge from a file or folder into the project vault.

Target: use whatever path the user specified after /absorb.
If no path was given, ask: "Which file or folder should I absorb?"

Steps:

1. Identify the target
   - If a file: read it
   - If a folder: list all .md files inside it and read each one

2. For each file, determine what kind of knowledge it contains and route accordingly:
   - Architecture / design notes → find or create `./bedrock/Memory/<topic>.md`
   - Decisions / ADRs → append structured entries to `./bedrock/Memory/decisions.md`
   - Changelog / history entries → append events to `./bedrock/History/events.ndjson`
   - API / component docs → find or create the relevant Memory branch note
   - Mix of the above → split and route each part to the right place

3. For each Memory branch you write to:
   - Update the Current State section with confirmed facts extracted from the file
   - Add a dated entry to Recent Changes: `YYYY-MM-DD -- absorbed from <source>`
   - Do NOT copy the file verbatim — extract only stable, confirmed facts
   - Skip speculative, transitional, or session-only content

4. If durable project context changed, update `./bedrock/Memory/PROJECT.md`
5. If current priorities changed, update `./bedrock/Work/NOW.md`

6. Run in terminal: `bedrock sync --project .`

7. Summarize:
   - Which files were read
   - Which Memory branches were updated or created
   - Which decisions were added
   - What was skipped and why
