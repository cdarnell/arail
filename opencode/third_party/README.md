# opencode/third_party

This directory is intended to host third-party code that the Opencode gateway or runtime expects to be available locally (for example `autoresearch`). For airgapped or offline installs, populate this path with the required repositories or extracted artifacts.

Expected layout for `autoresearch` integration (recommended):

- `opencode/third_party/autoresearch/` — a checked-out clone of the autoresearch project. The bootstrap script looks for this path when `Autoresearch` is provided interactively.

Example structure:

```
opencode/third_party/
└─ autoresearch/
   ├─ README.md
   ├─ requirements.txt
   ├─ src/
   └─ scripts/
```

How to populate (networked host -> airgapped host):

1. On a networked host:

```sh
git clone https://github.com/your-org/autoresearch.git autoresearch
tar -czf autoresearch.tar.gz autoresearch
```

2. Transfer `autoresearch.tar.gz` to the airgapped host and extract into this directory:

```sh
mkdir -p /path/to/minimalist/opencode/third_party
tar -xzf autoresearch.tar.gz -C /path/to/minimalist/opencode/third_party/
```

3. Ensure file ownership and permissions are correct for the runtime user.

Bootstrap notes:
- If the bootstrap detects a networked environment and you provided a repo URL, it may `git clone` into this path automatically.
- In airgapped setups, prefer providing tarballs or pre-built container images and update Helm values to point to local resources.

If you'd like, I can add a small helper script to `scripts/` that automates packing repositories for transfer. Ask me to create that next.
