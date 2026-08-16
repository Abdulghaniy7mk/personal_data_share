#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║          CYBERLAB - Hacking Tools Launcher (Mint)             ║
# ║         Rofi-based tool browser for Linux Mint                ║
# ╚══════════════════════════════════════════════════════════════╝
# Run: bash cyberlab-setup-mint.sh

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

CONFIG_DIR="$HOME/.config/cyberlab"
BIN="$HOME/.local/bin"

mkdir -p "$CONFIG_DIR" "$BIN"

echo -e "${CYAN}"
echo "  ██████╗██╗   ██╗██████╗ ███████╗██████╗ ██╗      █████╗ ██████╗ "
echo " ██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗██║     ██╔══██╗██╔══██╗"
echo " ██║      ╚████╔╝ ██████╔╝█████╗  ██████╔╝██║     ███████║██████╔╝"
echo " ██║       ╚██╔╝  ██╔══██╗██╔══╝  ██╔══██╗██║     ██╔══██║██╔══██╗"
echo " ╚██████╗   ██║   ██████╔╝███████╗██║  ██║███████╗██║  ██║██████╔╝"
echo "  ╚═════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝ "
echo -e "${NC} ${DIM}(mint edition)${NC}"

# ─────────────────────────────────────────────────────────────────
# 0. DEPENDENCY CHECK
# ─────────────────────────────────────────────────────────────────
echo -e "${GREEN}[0/4]${NC} Checking dependencies..."

if ! command -v rofi &>/dev/null; then
    echo -e "   ${RED}✗ rofi not found.${NC} Install with: ${DIM}sudo apt install rofi${NC}"
fi

# Pick whatever terminal actually exists on this box, in order of preference
TERMINAL=""
for t in kitty alacritty gnome-terminal xfce4-terminal mate-terminal x-terminal-emulator xterm; do
    command -v "$t" &>/dev/null && { TERMINAL="$t"; break; }
done

if [[ -z "$TERMINAL" ]]; then
    echo -e "   ${RED}✗ No terminal emulator found.${NC} Install one: ${DIM}sudo apt install xterm${NC}"
else
    echo -e "   ${DIM}→ using terminal: $TERMINAL${NC}"
fi

# ─────────────────────────────────────────────────────────────────
# 1. TOOLS DATABASE
# Format: name|category|description|help_flag
# help_flag: --help | -h | -help | --usage | (empty = just run)
# ─────────────────────────────────────────────────────────────────
echo -e "${GREEN}[1/4]${NC} Writing tools database..."

cat > "$CONFIG_DIR/tools.db" << 'EOF'
# CYBERLAB TOOLS DATABASE
# name|category|description|help_flag
#
# ── INFORMATION GATHERING ─────────────────────────────────────────
nmap|Recon|Network mapper - port scanning and host discovery|--help
masscan|Recon|Fastest TCP port scanner (100M pkt/sec)|--help
whois|Recon|Domain registration and IP ownership lookup|--help
theHarvester|Recon|Emails, subdomains, IPs from public sources|-h
recon-ng|Recon|Modular web reconnaissance framework|--help
subfinder|Recon|Fast passive subdomain discovery|-h
amass|Recon|Network surface attack mapping (deep OSINT)|-help
dnsx|Recon|Multi-purpose DNS toolkit|-h
dnsenum|Recon|DNS enumeration - zone transfer, brute force|--help
dnsrecon|Recon|DNS enumeration and zone walking|-h
fierce|Recon|DNS scanner for non-contiguous IP space|--help
netdiscover|Recon|ARP recon tool for local networks|-h
traceroute|Recon|Print the route packets take to network host|--help
arping|Recon|ARP ping utility|--help
#
# ── WEB APPLICATION ───────────────────────────────────────────────
sqlmap|WebApp|Automatic SQL injection and DB takeover tool|--help
nikto|WebApp|Web server vulnerability and config scanner|-Help
gobuster|WebApp|Dir/file/DNS/vhost brute-forcer (Go)|--help
dirb|WebApp|Web content scanner using wordlists|
ffuf|WebApp|Fast web fuzzer (dirs, params, vhosts)|-h
wfuzz|WebApp|Web application fuzzer|--help
whatweb|WebApp|Next-gen web fingerprinter (CMSs, versions)|--help
wafw00f|WebApp|Web Application Firewall fingerprinter|-h
commix|WebApp|Automated OS command injection|-h
xsstrike|WebApp|XSS detection and exploitation suite|-h
wpscan|WebApp|WordPress vulnerability scanner|-h
droopescan|WebApp|CMS vulnerability scanner (Drupal, etc)|-h
burpsuite|WebApp|Web app security testing platform (GUI)|
zaproxy|WebApp|OWASP ZAP web app security scanner|
#
# ── PASSWORD ATTACKS ──────────────────────────────────────────────
hashcat|Passwords|World's fastest GPU-based password recovery|--help
john|Passwords|John the Ripper - CPU password cracker|--help
hydra|Passwords|Fast parallelized network login brute-forcer|-h
medusa|Passwords|Parallel network login speed brute-forcer|--help
ncrack|Passwords|High-speed network authentication cracker|--help
crunch|Passwords|Custom wordlist generator by pattern|--help
cewl|Passwords|Website wordlist generator from keywords|-h
cupp|Passwords|Common User Passwords Profiler|-h
hashid|Passwords|Identify hash types from string|-h
hash-identifier|Passwords|Hash type identifier (Python tool)|
#
# ── EXPLOITATION ──────────────────────────────────────────────────
msfconsole|Exploitation|Metasploit Framework interactive console|-h
msfvenom|Exploitation|Metasploit payload encoder and generator|--help
searchsploit|Exploitation|Offline exploit database searcher|--help
exploitdb|Exploitation|Exploit database CLI|-h
beef-xss|Exploitation|Browser Exploitation Framework|
sqlninja|Exploitation|SQL Server injection and takeover|-h
#
# ── WIRELESS ──────────────────────────────────────────────────────
aircrack-ng|Wireless|802.11 WEP/WPA/WPA2 key cracker|--help
airmon-ng|Wireless|Enable/disable monitor mode on wireless|--help
airodump-ng|Wireless|802.11 packet capture tool|--help
aireplay-ng|Wireless|Wireless packet injector (deauth, fake)|--help
wifite|Wireless|Automated wireless network auditor|--help
kismet|Wireless|Wireless network detector and packet sniffer|--help
pixiewps|Wireless|WPS offline PIN cracker|--help
reaver|Wireless|WPS brute force attack tool|--help
bully|Wireless|WPS brute force attack (alternative to reaver)|--help
#
# ── SNIFFING & SPOOFING ───────────────────────────────────────────
wireshark|Sniffing|Graphical network protocol analyzer (GUI)|
tshark|Sniffing|Terminal-based Wireshark (CLI)|--help
tcpdump|Sniffing|Command-line packet capture and analyzer|--help
ettercap|Sniffing|MITM attacks - ARP spoofing, sniffing|--help
bettercap|Sniffing|Swiss army knife for network attacks|--help
arpspoof|Sniffing|ARP cache poisoning tool|-h
mitmproxy|Sniffing|Interactive HTTPS-capable MITM proxy|--help
responder|Sniffing|LLMNR/NBT-NS/MDNS poisoner and NTLM capture|-h
#
# ── FORENSICS ─────────────────────────────────────────────────────
binwalk|Forensics|Firmware and binary file analysis tool|--help
foremost|Forensics|File carving by file headers and footers|-h
photorec|Forensics|Recover lost files from disk|
testdisk|Forensics|Recover lost partitions|
strings|Forensics|Extract printable strings from binary files|--help
exiftool|Forensics|Read/write metadata in files|-h
hexedit|Forensics|Interactive hex editor|
xxd|Forensics|Hex dump and reverse hex dump|--help
file|Forensics|Determine file type|--help
volatility3|Forensics|Advanced memory forensics framework|-h
autopsy|Forensics|Digital forensics platform (GUI)|
#
# ── REVERSE ENGINEERING ───────────────────────────────────────────
gdb|RevEng|GNU Debugger - binary analysis and debugging|--help
radare2|RevEng|Reverse engineering framework + disassembler|--help
ghidra|RevEng|NSA reverse engineering suite (GUI)|
r2|RevEng|Radare2 shorthand launcher|--help
objdump|RevEng|Display info from object files|--help
readelf|RevEng|Display info about ELF format files|--help
strace|RevEng|Trace system calls and signals|--help
ltrace|RevEng|Trace library calls|--help
nm|RevEng|List symbols in object files|--help
upx|RevEng|Executable packer/unpacker|-h
pwndbg|RevEng|GDB plugin for exploit development|
peda|RevEng|Python Exploit Dev Assist for GDB|
#
# ── CRYPTOGRAPHY ──────────────────────────────────────────────────
openssl|Crypto|Cryptography and SSL/TLS toolkit|help
gpg|Crypto|GNU Privacy Guard - encryption and signing|--help
age|Crypto|Simple, modern file encryption|-h
steghide|Crypto|Steganography - hide data in image/audio|-h
stegsolve|Crypto|Steganography analysis tool|
zsteg|Crypto|Detect hidden data in PNG/BMP files|-h
#
# ── ANDROID ───────────────────────────────────────────────────────
adb|Android|Android Debug Bridge - control Android devices|--help
apktool|Android|APK reverse engineering and repackaging|-h
jadx|Android|DEX to Java decompiler|-h
dex2jar|Android|Convert DEX to JAR for Java decompilers|-h
androguard|Android|Python tool for Android app analysis|-h
frida|Android|Dynamic instrumentation toolkit|-h
objection|Android|Runtime mobile exploration toolkit|-h
#
# ── SOCIAL ENGINEERING ────────────────────────────────────────────
setoolkit|SocEng|Social Engineering Toolkit (SET)|
gophish|SocEng|Open-source phishing framework|-h
#
# ── OSINT ─────────────────────────────────────────────────────────
sherlock|OSINT|Find social media accounts by username|-h
maltego|OSINT|Link analysis and data mining platform (GUI)|
photon|OSINT|Fast web crawler for OSINT gathering|-h
holehe|OSINT|Check if email is registered on sites|-h
maigret|OSINT|Collect accounts by username (310+ sites)|-h
#
# ── NETWORK ───────────────────────────────────────────────────────
netcat|Network|Networking Swiss army knife|-h
socat|Network|Multipurpose relay tool|-h
proxychains|Network|Route connections through proxy chains|-h
tor|Network|Anonymity network daemon|--help
ncat|Network|Nmap's netcat replacement|-h
curl|Network|Transfer data to/from servers|--help
wget|Network|Network downloader|--help
ssh|Network|OpenSSH secure shell client|-h
EOF

echo -e "   ${DIM}→ $(grep -v '^#' "$CONFIG_DIR/tools.db" | grep -v '^$' | wc -l) tools registered${NC}"

# ─────────────────────────────────────────────────────────────────
# 2. ROFI THEME - Matrix / terminal hacker aesthetic
# (unchanged from the Arch version — rofi themes are distro-agnostic)
# ─────────────────────────────────────────────────────────────────
echo -e "${GREEN}[2/4]${NC} Creating rofi theme..."

cat > "$CONFIG_DIR/cyberlab.rasi" << 'EOF'
/**
 * CYBERLAB rofi theme
 * Matrix green on void black
 */

* {
    bg0:        #080808;
    bg1:        #0f1117;
    bg2:        #141820;
    bg-sel:     #0a1a0a;
    green:      #00ff41;
    green-dim:  #00802a;
    green-dark: #003d14;
    red:        #ff3333;
    white:      #cccccc;
    dim:        #444444;

    background-color: transparent;
    text-color:       @white;
    border-color:     @green;
    font:             "FantasqueSansM Nerd Font Bold 12";
}

window {
    background-color: @bg0;
    border:           1px solid;
    border-color:     @green;
    border-radius:    6px;
    width:            780px;
    padding:          0px;
    x-offset:         0;
    y-offset:         0;
    location:         center;
}

mainbox {
    background-color: transparent;
    children:         [ inputbar, message, listview ];
    spacing:          0;
}

/* ── Header bar ── */
inputbar {
    background-color: @bg2;
    border:           0 0 1px 0;
    border-color:     @green-dim;
    padding:          10px 16px;
    spacing:          10px;
    children:         [ prompt, textbox-prompt-sep, entry ];
}

prompt {
    background-color: transparent;
    text-color:       @green;
    font:             "FantasqueSansM Nerd Font Bold 13";
}

textbox-prompt-sep {
    str:              "│";
    text-color:       @green-dim;
    expand:           false;
    margin:           0 4px;
}

entry {
    background-color: transparent;
    text-color:       @green;
    placeholder:      "type to filter tools...";
    placeholder-color: @green-dark;
    cursor-color:     @green;
}

/* ── Info bar ── */
message {
    background-color: @bg1;
    border:           0 0 1px 0;
    border-color:     @bg2;
    padding:          5px 16px;
}

textbox {
    background-color: transparent;
    text-color:       @green-dim;
    font:             "FantasqueSansM Nerd Font 10";
}

/* ── Tool list ── */
listview {
    background-color: transparent;
    padding:          6px 4px;
    spacing:          1px;
    scrollbar:        false;
    lines:            16;
    fixed-height:     true;
}

element {
    background-color: transparent;
    border-radius:    3px;
    padding:          6px 14px;
    spacing:          0;
    orientation:      horizontal;
}

element normal.normal {
    background-color: transparent;
    text-color:       @white;
}

element alternate.normal {
    background-color: @bg1;
    text-color:       @white;
}

element selected.normal {
    background-color: @bg-sel;
    border:           0 0 0 2px;
    border-color:     @green;
    text-color:       @green;
}

element urgent.normal,
element selected.urgent {
    text-color: @red;
}

element-text {
    background-color: transparent;
    text-color:       inherit;
    vertical-align:   0.5;
}
EOF

# ─────────────────────────────────────────────────────────────────
# 3. MAIN LAUNCHER SCRIPT
# ─────────────────────────────────────────────────────────────────
echo -e "${GREEN}[3/4]${NC} Installing cyberlab launcher..."

cat > "$BIN/cyberlab" << 'SCRIPT'
#!/bin/bash
# ╔══════════════════════════════════════════╗
# ║  CYBERLAB - Hacking Tools Rofi Launcher  ║
# ╚══════════════════════════════════════════╝

CONFIG_DIR="$HOME/.config/cyberlab"
TOOLS_DB="$CONFIG_DIR/tools.db"
THEME="$CONFIG_DIR/cyberlab.rasi"

# Pick whatever terminal exists on this machine — Mint boxes vary
# (Cinnamon default has none of these preinstalled but xterm/gnome-terminal
# are one apt install away).
TERMINAL=""
for t in kitty alacritty gnome-terminal xfce4-terminal mate-terminal x-terminal-emulator xterm; do
    command -v "$t" &>/dev/null && { TERMINAL="$t"; break; }
done
if [[ -z "$TERMINAL" ]]; then
    notify-send "cyberlab" "No terminal emulator found. Install xterm or gnome-terminal." 2>/dev/null
    echo "No terminal emulator found. Try: sudo apt install xterm"
    exit 1
fi

# Category icons (nerd font)
declare -A CAT_ICONS=(
    [Recon]="󰍉 "
    [WebApp]="󰖟 "
    [Passwords]="󰌾 "
    [Exploitation]="󰚒 "
    [Wireless]="󰖩 "
    [Sniffing]="󰛳 "
    [Forensics]="󰙅 "
    [RevEng]="󰅺 "
    [Crypto]="󰌆 "
    [Android]="󰀲 "
    [SocEng]="󰱰 "
    [OSINT]="󰍹 "
    [Network]="󰈀 "
)

# Category display order
CAT_ORDER=(Recon WebApp Passwords Exploitation Wireless Sniffing Forensics RevEng Crypto Android SocEng OSINT Network)

# ── Build rofi menu ────────────────────────────────────────────────
build_menu() {
    declare -A cat_lines
    local total=0

    while IFS='|' read -r name category desc help_flag; do
        # Skip comments and empty lines
        [[ "$name" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$name" ]] && continue
        name="${name// /}"  # trim spaces

        # Only show installed tools
        command -v "$name" &>/dev/null || continue

        local icon="${CAT_ICONS[$category]:-  }"
        # Format: "icon [CAT] name ── description"
        cat_lines[$category]+="${icon}[${category}] ${name} ── ${desc}"$'\n'
        ((total++)) || true
    done < "$TOOLS_DB"

    # Output in category order
    for cat in "${CAT_ORDER[@]}"; do
        [[ -n "${cat_lines[$cat]}" ]] && printf "%s" "${cat_lines[$cat]}"
    done

    echo "__TOTAL__${total}" >&2
}

# ── Extract field from selection ────────────────────────────────────
get_toolname() {
    # Input format: "icon[CAT] toolname ── desc"
    # Extract word after "] "
    echo "$1" | grep -oP '\]\s+\K\S+'
}

# ── Get help command from DB ─────────────────────────────────────
get_help_flag() {
    local tool="$1"
    grep -m1 "^${tool}|" "$TOOLS_DB" | cut -d'|' -f4
}

get_description() {
    local tool="$1"
    grep -m1 "^${tool}|" "$TOOLS_DB" | cut -d'|' -f3
}

get_category() {
    local tool="$1"
    grep -m1 "^${tool}|" "$TOOLS_DB" | cut -d'|' -f2
}

# ── Open tool in terminal ──────────────────────────────────────────
launch_tool() {
    local tool="$1"
    local flag="$2"
    local desc="$3"
    local cat="$4"

    # Build the command to show in terminal
    local run_cmd
    if [[ -z "$flag" ]]; then
        # No flag - just run it (shows banner by itself)
        run_cmd="$tool"
    else
        run_cmd="$tool $flag"
    fi

    local body="
printf '\n'
printf '  \033[0;32m╔══════════════════════════════════════════════════════╗\033[0m\n'
printf '  \033[0;32m║\033[0m  \033[1;32m⚡ CYBERLAB\033[0m  \033[2m─\033[0m  Tool Reference Viewer               \033[0;32m║\033[0m\n'
printf '  \033[0;32m╠══════════════════════════════════════════════════════╣\033[0m\n'
printf '  \033[0;32m║\033[0m  \033[1mTool:\033[0m    \033[0;32m%-44s\033[0m\033[0;32m║\033[0m\n' '$tool'
printf '  \033[0;32m║\033[0m  \033[1mCategory:\033[0m \033[2m%-43s\033[0m\033[0;32m║\033[0m\n' '$cat'
printf '  \033[0;32m║\033[0m  \033[1mAbout:\033[0m   \033[2m%-44s\033[0m\033[0;32m║\033[0m\n' '$desc'
printf '  \033[0;32m║\033[0m  \033[1mCommand:\033[0m \033[33m%-44s\033[0m\033[0;32m║\033[0m\n' '$run_cmd'
printf '  \033[0;32m╚══════════════════════════════════════════════════════╝\033[0m\n'
printf '\n'
printf '  \033[2m── Output ─────────────────────────────────────────────\033[0m\n\n'
$run_cmd 2>&1
printf '\n'
printf '  \033[2m── Manual ─────────────────────────────────────────────\033[0m\n'
printf '  \033[2mRun: man $tool  |  $tool --help  |  $tool -h\033[0m\n'
printf '\n'
printf '  \033[0;32m[press any key to close]\033[0m '
read -rn1
"

    # Different terminals want the "run this and exec a shell" flag spelled differently
    case "$TERMINAL" in
        kitty)
            "$TERMINAL" --title "cyberlab :: $tool" --override "font_size=13" sh -c "$body" &
            ;;
        alacritty)
            "$TERMINAL" --title "cyberlab :: $tool" -e sh -c "$body" &
            ;;
        gnome-terminal)
            "$TERMINAL" --title="cyberlab :: $tool" -- sh -c "$body" &
            ;;
        xfce4-terminal|mate-terminal)
            "$TERMINAL" --title="cyberlab :: $tool" -e "sh -c \"$body\"" &
            ;;
        *)
            "$TERMINAL" -T "cyberlab :: $tool" -e sh -c "$body" &
            ;;
    esac
}

# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

# Count installed tools for header
MENU=$(build_menu 2>/tmp/cyberlab_meta)
INSTALLED=$(grep -c '.' <<< "$MENU" || echo 0)
TOTAL=$(grep -c '|' "$TOOLS_DB" || echo 0)

SELECTION=$(echo "$MENU" | rofi \
    -dmenu \
    -i \
    -p "⚡ cyberlab" \
    -mesg "  ${INSTALLED} tools installed  │  wordlist has ${TOTAL}+ known  │  select to view usage" \
    -theme "$THEME" \
    -no-custom \
    -format s \
    -markup-rows \
    2>/dev/null)

[[ -z "$SELECTION" ]] && exit 0

TOOL=$(get_toolname "$SELECTION")
[[ -z "$TOOL" ]] && exit 1

FLAG=$(get_help_flag "$TOOL")
DESC=$(get_description "$TOOL")
CAT=$(get_category "$TOOL")

launch_tool "$TOOL" "$FLAG" "$DESC" "$CAT"
SCRIPT

chmod +x "$BIN/cyberlab"

# ─────────────────────────────────────────────────────────────────
# 4. PRINT SETUP SUMMARY
# ─────────────────────────────────────────────────────────────────
echo -e "${GREEN}[4/4]${NC} Done!\n"

TOOL_COUNT=$(grep -v '^#' "$CONFIG_DIR/tools.db" | grep -v '^$' | wc -l)

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}✓${NC} Launcher :  ${GREEN}$BIN/cyberlab${NC}"
echo -e "  ${GREEN}✓${NC} Tools DB :  ${GREEN}$CONFIG_DIR/tools.db${NC} (${TOOL_COUNT} tools)"
echo -e "  ${GREEN}✓${NC} Rofi Theme: ${GREEN}$CONFIG_DIR/cyberlab.rasi${NC}"
echo -e "  ${GREEN}✓${NC} Terminal :  ${GREEN}${TERMINAL:-none detected}${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}HOW TO RUN:${NC}"
echo -e "  ${DIM}\$${NC} cyberlab"
echo -e "  ${DIM}(make sure ~/.local/bin is in your \$PATH)${NC}"
echo ""
echo -e "  ${GREEN}KEYBOARD SHORTCUT${NC} (Cinnamon):"
echo -e "  ${DIM}Settings → Keyboard → Shortcuts → Custom Shortcuts → Add${NC}"
echo -e "  ${DIM}Command: $BIN/cyberlab   |   bind to whatever key you like${NC}"
echo ""
echo -e "  ${GREEN}INSTALL rofi (if missing):${NC}"
echo -e "  ${DIM}sudo apt update && sudo apt install rofi${NC}"
echo ""
echo -e "  ${GREEN}INSTALL TOOLS — Ubuntu/Mint repos have a good chunk directly:${NC}"
echo -e "  ${DIM}sudo apt install nmap masscan whois traceroute sqlmap nikto \\${NC}"
echo -e "  ${DIM}    gobuster dirb wfuzz whatweb hydra john hashcat crunch \\${NC}"
echo -e "  ${DIM}    aircrack-ng kismet wireshark tcpdump ettercap-graphical \\${NC}"
echo -e "  ${DIM}    bettercap binwalk foremost testdisk exiftool gdb radare2 \\${NC}"
echo -e "  ${DIM}    steghide adb apktool netcat-openbsd socat proxychains4 tor${NC}"
echo ""
echo -e "  ${GREEN}TOOLS NOT IN DEFAULT REPOS${NC} (Go tools, BlackArch-only, etc):"
echo -e "  ${DIM}Option A — add the Kali repo as an EXTRA source (don't full-upgrade):${NC}"
echo -e "  ${DIM}  echo 'deb http://http.kali.org/kali kali-rolling main' | \\${NC}"
echo -e "  ${DIM}    sudo tee /etc/apt/sources.list.d/kali.list${NC}"
echo -e "  ${DIM}  curl -fsSL https://archive.kali.org/archive-key.asc | \\${NC}"
echo -e "  ${DIM}    sudo gpg --dearmor -o /usr/share/keyrings/kali.gpg${NC}"
echo -e "  ${DIM}  # then pin it low-priority (400) so it never overrides Mint's own${NC}"
echo -e "  ${DIM}  # packages, and install single tools with -t kali-rolling${NC}"
echo -e "  ${DIM}Option B — install standalone (safer, no repo pinning games):${NC}"
echo -e "  ${DIM}  go install (subfinder, amass, ffuf, dnsx...) via Go toolchain${NC}"
echo -e "  ${DIM}  pipx install (theHarvester, sherlock, holehe, maigret...)${NC}"
echo -e "  ${DIM}  Metasploit: curl https://raw.githubusercontent.com/rapid7/ \\${NC}"
echo -e "  ${DIM}    metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/ \\${NC}"
echo -e "  ${DIM}    msfupdate.erb > msfinstall && chmod +x msfinstall && ./msfinstall${NC}"
echo ""
echo -e "  ${GREEN}ADD YOUR OWN TOOLS${NC} — edit the DB:"
echo -e "  ${DIM}nano $CONFIG_DIR/tools.db${NC}"
echo -e "  ${DIM}# Format: name|Category|description|--help-flag${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
