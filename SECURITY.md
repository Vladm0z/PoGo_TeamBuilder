# Security

## Attack surface

This tool makes outbound HTTP GET requests to pvpoke.com, writes JSON and JS
files into a local cache directory, and executes JavaScript with Node.

## Relevant properties

- Downloaded JSON is parsed before being written to the cache, so a malformed
  response cannot leave a corrupt file behind.
- PvPoke's battle scripts are executed inside a Node `vm` context, not in the
  host process, with a stub jQuery that only serves the local gamemaster file.
  That context has filesystem access through the harness however, since it reads
  the script files themselves: treat the cache directory as code.
- No account credentials, tokens or personal data are used or stored.
- No input from `--mons` or `--file` is passed to a shell. Species names are
  matched against the gamemaster; the only subprocess is `node harness.js` with
  a JSON payload on stdin.

## Reporting

Open an issue for anything that is not exploitable, and a private security
advisory for anything that is. There is no bounty.
