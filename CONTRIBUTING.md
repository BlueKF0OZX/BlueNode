# Contributing to BlueNode

BlueNode is alpha software for AllStarLink v3. Keep changes small and describe
the operator-visible problem, the resulting behavior, and any remaining limits.

1. Start a branch from the latest `main` and make one focused change.
2. Use public example configuration and disposable fixtures. Never commit live
   configuration, credentials, reports, recordings, or private station data.
3. Follow [Testing](docs/TESTING.md). Run the checks relevant to the change and
   include their results in the pull request. GitHub also requires the core,
   dashboard, and repository checks to pass on an up-to-date branch.
4. For dashboard changes, check phone and desktop layouts. Verify saved favorites
   and labels across independent browsers when changing preference behavior;
   document whether data is local to a browser or shared by the node.
5. For controls or installation changes, include failure and rollback behavior.
   Tests must not connect to an operating radio or change its configuration.

Open a pull request with a clear description and validation evidence. Passing
fixture tests does not establish real RF/audio behavior, hardware compatibility,
or endurance. Keep those claims tied to actual evidence and the
[validation status](docs/VALIDATION_STATUS.md).

Report ordinary bugs using the repository's issue templates. For vulnerabilities,
follow [Security](SECURITY.md) before sharing technical details publicly.

Publishing source or merging a pull request does not authorize deployment to
an operating node. Deployment and supervised radio acceptance are separate steps.
