# Security
The attack surface is small: outbound HTTP GET requests to pvpoke.com, JSON and JS files written to a local cache directory, and JavaScript executed with Node.

- Downloaded JSON is parsed before it is written, so a malformed response cannot leave a corrupt file behind.
- PvPoke's battle scripts run inside a Node `vm` context rather than the host process, with a stub jQuery that serves only the local gamemaster. That context can read the cached script files, so treat the cache directory as code.
- No account credentials, tokens or personal data are used or stored.
- No input from `--mons` or `--file` reaches a shell. Species names are matched against the gamemaster, and the only subprocess is `node harness.js` with a JSON payload on stdin.

Report anything not exploitable as a normal issue, and anything exploitable as a private security advisory. There is no bounty.
