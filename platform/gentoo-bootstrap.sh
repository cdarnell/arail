#!/usr/bin/env bash
# =============================================================================
# OGLab — Gentoo System Bootstrap
#
# Run this ONCE on a fresh Gentoo install to compile the full AI lab stack:
#   - Python + ML libraries
#   - WezTerm (terminal)
#   - ttyd (terminal-in-browser)
#   - Jupyter
#   - Avahi (mDNS for oglab.local)
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

info()  { echo -e "${GREEN}[oglab]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[oglab]${RESET} $*"; }
error() { echo -e "${RED}[oglab]${RESET} $*"; exit 1; }

[[ $EUID -eq 0 ]] || error "Run as root: sudo $0"

# ── USE flags ────────────────────────────────────────────────────────────
info "Configuring USE flags…"

mkdir -p /etc/portage/package.use

cat > /etc/portage/package.use/oglab <<'EOF'
# OGLab AI Lab stack
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

# ── mDNS: Avahi (oglab.local) ───────────────────────────────────────────
info "Installing Avahi for oglab.local…"
emerge -av --noreplace net-dns/avahi

# Configure oglab.local service
mkdir -p /etc/avahi/services
cat > /etc/avahi/services/oglab.service <<'EOF'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>OGLab AI Portal</name>
  <service>
    <type>_http._tcp</type>
    <port>8080</port>
    <txt-record>path=/</txt-record>
  </service>
</service-group>
EOF

rc-update add avahi-daemon default
rc-service avahi-daemon start

# Set hostname to oglab
hostnamectl set-hostname oglab 2>/dev/null || echo "oglab" > /etc/hostname
info "Hostname set to oglab → accessible as oglab.local"

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
info "Jupyter will be installed in the OGLab venv by setup.sh"

# ── OpenRC services ──────────────────────────────────────────────────────
info "Creating OGLab services…"

# Portal service
cat > /etc/init.d/oglab-portal <<'INITEOF'
#!/sbin/openrc-run

name="oglab-portal"
description="OGLab AI Lab Portal (FastAPI)"
command="/opt/oglab/.venv/bin/uvicorn"
command_args="portal.app:app --host 0.0.0.0 --port 8080"
directory="/opt/oglab"
pidfile="/run/${RC_SVCNAME}.pid"
command_background="yes"
command_user="oglab"
output_log="/var/log/oglab-portal.log"
error_log="/var/log/oglab-portal.log"

depend() {
    need net
    after avahi-daemon
}
INITEOF
chmod +x /etc/init.d/oglab-portal

# ttyd service
cat > /etc/init.d/oglab-terminal <<'INITEOF'
#!/sbin/openrc-run

name="oglab-terminal"
description="OGLab browser terminal (ttyd + zsh)"
command="/usr/bin/ttyd"
command_args="-W -p 7681 /bin/zsh"
pidfile="/run/${RC_SVCNAME}.pid"
command_background="yes"
command_user="oglab"

depend() {
    need net
}
INITEOF
chmod +x /etc/init.d/oglab-terminal

# Enable services
rc-update add oglab-portal default
rc-update add oglab-terminal default

# ── OGLab user ───────────────────────────────────────────────────────────
if ! id oglab &>/dev/null; then
    useradd -m -s /bin/zsh oglab
    info "Created user: oglab"
fi

# ── Clone / install OGLab ───────────────────────────────────────────────
if [[ ! -d /opt/oglab ]]; then
    info "Cloning OGLab into /opt/oglab…"
    git clone https://github.com/cdarnell/minimalist-blueprint.git /opt/oglab
    chown -R oglab:oglab /opt/oglab
fi

su - oglab -c "cd /opt/oglab && ./setup.sh"

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
info "═══════════════════════════════════════════════════"
info "  OGLab installed!"
info ""
info "  Portal:   http://oglab.local:8080"
info "  Terminal:  http://oglab.local:7681"
info "  Jupyter:   http://oglab.local:8888"
info ""
info "  Start now:  rc-service oglab-portal start"
info "              rc-service oglab-terminal start"
info "═══════════════════════════════════════════════════"
