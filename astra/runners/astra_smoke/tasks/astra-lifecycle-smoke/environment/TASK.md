# Durable recovery contract

The task-owned checkpoint is `/app/recovery.json`.

If its `status` is `resume-required`, run the exact `resume_command` stored in
that file. Do not write `/app/result.txt` or edit the checkpoint directly.
After the command exits, verify that the checkpoint status is `complete` and
that `/app/result.txt` contains the expected result.
