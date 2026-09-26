# Security reporting

BlueNode is alpha software. Security fixes target the current development branch;
older alpha builds have no guaranteed backport or response-time commitment.

Use GitHub's private [Report a vulnerability](https://github.com/BlueKF0OZX/BlueNode/security/advisories/new)
form for suspected vulnerabilities. Include the affected revision, a minimal
reproduction using synthetic data, expected and actual behavior, and likely impact.
Do not attach passwords, tokens, complete live configuration, or unfiltered logs.

If private reporting is unavailable, open an issue asking for a private contact
channel without disclosing the vulnerability or sensitive data. Do not publish
exploitation details in a normal issue before coordinated review.

Keep the dashboard on a trusted interface or use the documented authenticated
access setup. See [Remote access](docs/REMOTE_ACCESS.md) and
[Remote Admin](docs/REMOTE_ADMIN.md). Test reports against an isolated fixture;
do not probe someone else's node or trigger radio controls without permission.
