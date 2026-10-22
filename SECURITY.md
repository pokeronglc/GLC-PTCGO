# Security policy

GLC-PTCGO is preservation and interoperability software for a discontinued
game client. It has not been hardened as a public internet service.

## Safe deployment

- Run the server on a trusted private network unless you have independently
  reviewed and secured the deployment.
- Keep the administrator password printed by `setup_db.py` private, and change
  it from the admin page if it was ever shared.
- Never commit `server.key`, account databases, logs, extracted client files,
  or cbrew bundles.
- Keep the supported PTCGO client and the server isolated from sensitive
  systems and credentials.

## Reporting a vulnerability

Open a private GitHub security advisory in the GLC-PTCGO repository. Do not
include real credentials, private keys, account databases, or proprietary game
assets in the report.
