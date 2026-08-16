---
name: dummy
description: A dummy sub-agent for testing the registry. Prints hello and exits.
allowed-tools: [Bash]
orchestrator:
  output_contract:
    type: object
    required: [output_paths, summary]
    schema:
      type: object
      properties:
        output_paths: {type: object}
        summary: {type: string}
  timeout_seconds: 60
---
You are a dummy sub-agent. Run `echo "hello from dummy" > <scratch_dir>/output.txt` and write a contract.json file to <scratch_dir>/contract.json with {"output_paths": {"output": "<scratch_dir>/output.txt"}, "summary": "Said hello"}.