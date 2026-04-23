
#!/usr/bin/env bash
# =============================================================================
# Arail — Gentoo System Bootstrap
#
# Run this ONCE on a fresh Gentoo install to compile the full AI lab stack:
#   - Python + ML libraries
#   - WezTerm (terminal)
#   - ttyd (terminal-in-browser)
#   - Jupyter
#   - Avahi (mDNS for arail.local)
#   - Nvidia/CUDA (if GPU present)
#   - FastAPI portal dependencies
#
# Usage:  sudo ./platform/gentoo-bootstrap.sh
# =============================================================================
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { echo -e "${GREEN}[arail]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[arail]${RESET} $*"; }
error() { echo -e "${RED}[arail]${RESET} $*"; exit 1; }

[[ $EUID -eq 0 ]] || error "Run as root: sudo $0"

# ── USE flags ────────────────────────────────────────────────────────────
info "Configuring USE flags…"

mkdir -p /etc/portage/package.use

cat > /etc/portage/package.use/arail <<'EOF'
# Arail AI Lab stack
dev-lang/python sqlite readline
dev-python/numpy lapack
sci-libs/pytorch cuda
dev-util/nvidia-cuda-toolkit -profiler
net-dns/avahi mdnsresponder-compat dbus
gui-apps/wezterm wayland
EOF

# ── Core system ──────────────────────────────────────────────────────────
info "Installing core packages…"

emerge --update --newuse --deep @world

emerge -av --noreplace \
    dev-lang/python \
    dev-python/pip \
    dev-python/virtualenv \
    sys-devel/gcc \
    dev-build/cmake \
    net-misc/curl \
    dev-vcs/git

# ── Terminal: WezTerm ────────────────────────────────────────────────────
info "Installing WezTerm…"
emerge -av --noreplace gui-apps/wezterm || {
    warn "WezTerm not in Portage tree — installing from binary release"
    # Fallback: download from GitHub releases
    WEZTERM_VER="20240203-110809-5046fc22"
    curl -sLO "https://github.com/wez/wezterm/releases/download/${WEZTERM_VER}/WezTerm-${WEZTERM_VER}-Ubuntu22.04.AppImage"
    chmod +x WezTerm-*.AppImage
    mv WezTerm-*.AppImage /usr/local/bin/wezterm
}

# ── ttyd (terminal in browser) ──────────────────────────────────────────
info "Installing ttyd…"
emerge -av --noreplace net-misc/ttyd || {
    warn "ttyd not in Portage — building from source"
    git clone --depth 1 https://github.com/tsl0922/ttyd.git /tmp/ttyd-build
    cd /tmp/ttyd-build && mkdir build && cd build
    cmake .. && make && make install
    cd / && rm -rf /tmp/ttyd-build
}

# ── mDNS: Avahi (arail.local) ───────────────────────────────────────────
info "Installing Avahi for arail.local…"
emerge -av --noreplace net-dns/avahi

# Configure arail.local service
mkdir -p /etc/avahi/services
cat > /etc/avahi/services/arail.service <<'EOF'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>Arail AI Portal</name>
  <service>
    <type>_http._tcp</type>
    <port>8080</port>
    <txt-record>path=/</txt-record>
  </service>
</service-group>
EOF

rc-update add avahi-daemon default
rc-service avahi-daemon start

# Set hostname to arail
hostnamectl set-hostname arail 2>/dev/null || echo "arail" > /etc/hostname
info "Hostname set to arail → accessible as arail.local"

# ── GPU: Nvidia (if detected) ───────────────────────────────────────────
if lspci | grep -qi nvidia; then
    info "Nvidia GPU detected — installing drivers + CUDA…"

    echo "x11-drivers/nvidia-drivers NVIDIA-r2" >> /etc/portage/package.license/nvidia
    emerge -av --noreplace \
        x11-drivers/nvidia-drivers \
        dev-util/nvidia-cuda-toolkit

    modprobe nvidia 2>/dev/null || true
    nvidia-smi && info "Nvidia driver loaded" || warn "nvidia-smi failed — check kernel config"
else
    info "No Nvidia GPU detected — skipping CUDA"
fi

# ── Python ML stack ──────────────────────────────────────────────────────
info "Installing Python dependencies into system…"
emerge -av --noreplace \
    dev-python/numpy \
    dev-python/scipy

# ── Jupyter ──────────────────────────────────────────────────────────────
info "Jupyter will be installed in the Arail venv by setup.sh"

# ── OpenRC services ──────────────────────────────────────────────────────
info "Creating Arail services…"

# Portal service
cat > /etc/init.d/arail-portal <<'INITEOF'
#!/sbin/openrc-run
# Arail portal — binds to 127.0.0.1 by default.
#
# WARNING: moving off 127.0.0.1 is explicit opt-out of the security model.
# The portal has no built-in auth beyond the code-server password. If you
# want to expose it beyond the local machine, terminate TLS + auth on a
# reverse proxy (nginx, caddy, traefik) and point it at 127.0.0.1:8080.
# See SECURITY.md.

name="arail-portal"
description="Arail AI Lab Portal (FastAPI)"
command="/opt/arail/.venv/bin/uvicorn"
command_args="arail.portal.app:app --host 127.0.0.1 --port 8080"
directory="/opt/arail"
pidfile="/run/${RC_SVCNAME}.pid"
command_background="yes"
command_user="arail"
output_log="/var/log/arail-portal.log"
error_log="/var/log/arail-portal.log"

depend() {
    need net
    after avahi-daemon
}
INITEOF
chmod +x /etc/init.d/arail-portal

# ttyd service
cat > /etc/init.d/arail-terminal <<'INITEOF'
#!/sbin/openrc-run

name="arail-terminal"
description="Arail browser terminal (ttyd + zsh)"
command="/usr/bin/ttyd"
command_args="-W -p 7681 -t scrollBar=true /bin/zsh"
pidfile="/run/${RC_SVCNAME}.pid"
command_background="yes"
command_user="arail"

depend() {
    need net
}
INITEOF
chmod +x /etc/init.d/arail-terminal

# Enable services
rc-update add arail-portal default
rc-update add arail-terminal default

# ── Arail user ───────────────────────────────────────────────────────────
if ! id arail &>/dev/null; then
    useradd -m -s /bin/zsh arail
    info "Created user: arail"
fi

# ── Clone / install Arail ───────────────────────────────────────────────
if [[ ! -d /opt/arail ]]; then
    info "Cloning Arail into /opt/arail…"
    git clone https://github.com/cdarnell/autoresearch-lab.git /opt/arail
    chown -R arail:arail /opt/arail
fi

su - arail -c "cd /opt/arail && ./setup.sh"

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
info "═══════════════════════════════════════════════════"
info "  Arail installed!"
info ""
info "  Portal:   http://arail.local:8080"
info "  Terminal:  http://arail.local:7681"
info "  Jupyter:   http://arail.local:8888"
info ""
info "  Start now:  rc-service arail-portal start"
info "              rc-service arail-terminal start"
info "═══════════════════════════════════════════════════"
