#!/usr/bin/env bash
# =============================================================================
#  BwanaFacturation — Installation du SERVEUR WEB (portail public)
#  Serveur : srv1894892.hstgr.cloud (2.24.110.102)
#  Domaine : bwanafacturation.bwhub.tech
#  Chemin  : /var/www/apps/BwanaFacturation
#
#  Rôle : terminaison HTTPS (Let's Encrypt) + reverse proxy vers le backend
#         (2.25.102.16:8080). Aucun code applicatif ni base de données ici.
#
#  PRÉREQUIS (dans cet ordre) :
#     1. Enregistrement DNS  A  bwanafacturation.bwhub.tech → 2.24.110.102
#     2. install_bd.sh terminé avec succès sur le serveur BD
#
#  Usage :   sudo LE_EMAIL=vous@exemple.com bash install_web.sh
# =============================================================================
set -Eeuo pipefail
trap 'echo -e "\n\033[1;31m[ERREUR]\033[0m ligne $LINENO : la commande « $BASH_COMMAND » a échoué." >&2' ERR

# ----------------------------- PARAMÈTRES ------------------------------------
APP_NAME="BwanaFacturation"
APP_ROOT="/var/www/apps"
APP_DIR="${APP_ROOT}/${APP_NAME}"
DOMAIN="${DOMAIN:-bwanafacturation.bwhub.tech}"
WEB_SERVER_IP="${WEB_SERVER_IP:-2.24.110.102}"
BACKEND_IP="${BACKEND_IP:-2.25.102.16}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
LE_EMAIL="${LE_EMAIL:-}"
ENABLE_UFW="${ENABLE_UFW:-yes}"
SKIP_DNS_CHECK="${SKIP_DNS_CHECK:-0}"          # 1 si le DNS passe par un proxy (ex. Cloudflare)
SKIP_BACKEND_CHECK="${SKIP_BACKEND_CHECK:-0}"

SITE="bwanafacturation"
log()  { echo -e "\033[1;34m[WEB]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[ OK ]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $*"; }
die()  { echo -e "\033[1;31m[FATAL]\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Lancez ce script en root (sudo bash install_web.sh)."
command -v apt-get >/dev/null || die "Ce script supporte Debian/Ubuntu (apt)."
cd /

# ------------------------- 1. PRÉ-VÉRIFICATIONS ------------------------------
log "1/8 Pré-vérifications…"
if [[ "${SKIP_DNS_CHECK}" != "1" ]]; then
    RESOLVED="$(getent ahostsv4 "${DOMAIN}" | awk '{print $1}' | sort -u | tr '\n' ' ' | sed 's/ $//')"
    [[ -n "${RESOLVED}" ]] || die "Le domaine ${DOMAIN} ne se résout pas encore. Créez l'enregistrement DNS A → ${WEB_SERVER_IP}, attendez la propagation, puis relancez."
    [[ "${RESOLVED}" == "${WEB_SERVER_IP}" ]] || die "DNS : ${DOMAIN} pointe vers « ${RESOLVED} » au lieu de ${WEB_SERVER_IP}. Corrigez l'enregistrement A (ou SKIP_DNS_CHECK=1 si proxy DNS)."
    ok "DNS : ${DOMAIN} → ${RESOLVED}"
fi
if [[ -z "${LE_EMAIL}" ]]; then
    warn "LE_EMAIL non défini : le certificat sera créé sans e-mail de contact (pas d'alerte d'expiration)."
fi

# --------------------------- 2. PAQUETS SYSTÈME ------------------------------
log "2/8 Installation de nginx, certbot, ufw…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx certbot ufw curl ca-certificates >/dev/null
ok "Paquets installés ($(nginx -v 2>&1 | cut -d/ -f2))."

# --------------------- 3. TEST DE LIAISON AVEC LE BACKEND --------------------
log "3/8 Test de la liaison avec le backend (${BACKEND_IP}:${BACKEND_PORT})…"
if [[ "${SKIP_BACKEND_CHECK}" != "1" ]]; then
    HC="$(curl -s -o /dev/null -m 10 -w '%{http_code}' -H "Host: ${DOMAIN}" \
          "http://${BACKEND_IP}:${BACKEND_PORT}/BwanaFacturation/users/connexion/" || true)"
    [[ "${HC}" == "200" ]] || die "Backend injoignable ou en erreur (HTTP ${HC:-000}).
     - install_bd.sh a-t-il été exécuté avec succès sur ${BACKEND_IP} ?
     - Le pare-feu Hostinger (hPanel) autorise-t-il ${WEB_SERVER_IP} → ${BACKEND_IP}:${BACKEND_PORT} ?"
    ok "Backend joignable (page de connexion : HTTP 200)."
fi

# -------------------------- 4. ARBORESCENCE & PAGES --------------------------
log "4/8 Arborescence ${APP_DIR}…"
mkdir -p "${APP_DIR}/public/.well-known/acme-challenge" "${APP_DIR}/public/errors" \
         "${APP_DIR}/logs" /var/cache/nginx/bwana_static
chmod 755 "${APP_ROOT}" "${APP_DIR}" "${APP_DIR}/public"

cat > "${APP_DIR}/public/errors/50x.html" <<'HTML_EOF'
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>BwanaFacturation — Service momentanément indisponible</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#f4f6fa;color:#1f2a44}
  main{max-width:34rem;margin:1rem;padding:2.5rem 2rem;background:#fff;border-radius:14px;
       box-shadow:0 8px 30px rgba(20,30,60,.10);text-align:center}
  h1{font-size:1.4rem;margin:0 0 .75rem} p{line-height:1.55;margin:.5rem 0;color:#4a5568}
  .dot{width:14px;height:14px;border-radius:50%;background:#e8a317;display:inline-block;margin-bottom:1rem}
  small{color:#8a94a6}
</style>
</head>
<body>
<main>
  <span class="dot"></span>
  <h1>Service momentanément indisponible</h1>
  <p>BwanaFacturation est en cours de maintenance ou redémarre. Vos données ne sont pas affectées.</p>
  <p>Cette page se rafraîchit automatiquement toutes les 30&nbsp;secondes.</p>
  <small>Si le problème persiste, contactez l'administrateur.</small>
</main>
</body>
</html>
HTML_EOF
printf 'User-agent: *\nDisallow: /\n' > "${APP_DIR}/public/robots.txt"
chmod -R a+rX "${APP_DIR}/public"
ok "Pages d'erreur et robots.txt en place."

# ---------------------------- 5. NGINX (zones) -------------------------------
log "5/8 Configuration nginx…"
rm -f /etc/nginx/sites-enabled/default

cat > "/etc/nginx/conf.d/${SITE}-zones.conf" <<'ZONES_EOF'
# BwanaFacturation — zones partagées (contexte http)
upstream bwana_backend {
    server @@BACKEND_IP@@:@@BACKEND_PORT@@ max_fails=3 fail_timeout=10s;
    keepalive 16;
}
limit_req_zone $binary_remote_addr zone=bwana_login:10m  rate=20r/m;
limit_req_zone $binary_remote_addr zone=bwana_global:10m rate=30r/s;
limit_req_status 429;
proxy_cache_path /var/cache/nginx/bwana_static levels=1:2 keys_zone=bwana_static:10m
                 max_size=200m inactive=7d use_temp_path=off;
ZONES_EOF

# --- Étape A : vhost HTTP seul, pour obtenir le certificat (défi ACME) ---
cat > "/etc/nginx/sites-available/${SITE}" <<'HTTP_EOF'
server {
    listen 80;
    server_name @@DOMAIN@@;
    server_tokens off;
    location ^~ /.well-known/acme-challenge/ { root @@APP_DIR@@/public; }
    location / { return 301 https://$host$request_uri; }
}
HTTP_EOF
ln -sf "/etc/nginx/sites-available/${SITE}" "/etc/nginx/sites-enabled/${SITE}"

render() {   # remplace les @@VARIABLES@@
    sed -i -e "s|@@DOMAIN@@|${DOMAIN}|g" -e "s|@@APP_DIR@@|${APP_DIR}|g" \
           -e "s|@@BACKEND_IP@@|${BACKEND_IP}|g" -e "s|@@BACKEND_PORT@@|${BACKEND_PORT}|g" "$@"
}
render "/etc/nginx/conf.d/${SITE}-zones.conf" "/etc/nginx/sites-available/${SITE}"
nginx -t
systemctl enable nginx >/dev/null
systemctl reload nginx 2>/dev/null || systemctl restart nginx

# ------------------------- 6. CERTIFICAT LET'S ENCRYPT -----------------------
log "6/8 Certificat Let's Encrypt pour ${DOMAIN}…"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"
if [[ -s "${CERT_DIR}/fullchain.pem" ]]; then
    ok "Certificat déjà présent — conservé."
else
    if [[ -n "${LE_EMAIL}" ]]; then EMAIL_ARGS=(-m "${LE_EMAIL}"); else EMAIL_ARGS=(--register-unsafely-without-email); fi
    certbot certonly --webroot -w "${APP_DIR}/public" -d "${DOMAIN}" \
        --non-interactive --agree-tos "${EMAIL_ARGS[@]}" \
        || die "Échec Let's Encrypt. Vérifiez : DNS correct, port 80 ouvert (pare-feu Hostinger inclus)."
    ok "Certificat obtenu."
fi
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK_EOF'
#!/bin/sh
systemctl reload nginx
HOOK_EOF
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# ------------------------- 7. VHOST HTTPS DÉFINITIF --------------------------
log "7/8 Activation du vhost HTTPS (reverse proxy)…"
cat > "/etc/nginx/sites-available/${SITE}" <<'SITE_EOF'
# BwanaFacturation — portail public

# Port 80 : tout en HTTPS (sauf défi ACME de Let's Encrypt)
server {
    listen 80;
    server_name @@DOMAIN@@;
    server_tokens off;
    location ^~ /.well-known/acme-challenge/ { root @@APP_DIR@@/public; }
    location / { return 301 https://$host$request_uri; }
}

# Toute requête HTTP vers un autre nom de domaine / l'IP brute : fermée
server {
    listen 80 default_server;
    server_name _;
    return 444;
}

server {
    listen 443 ssl http2;
    server_name @@DOMAIN@@;
    server_tokens off;

    ssl_certificate     /etc/letsencrypt/live/@@DOMAIN@@/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/@@DOMAIN@@/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache   shared:SSL_bwana:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    access_log @@APP_DIR@@/logs/access.log;
    error_log  @@APP_DIR@@/logs/error.log warn;

    client_max_body_size 10m;
    gzip on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types text/css application/javascript application/json image/svg+xml text/plain;

    limit_req zone=bwana_global burst=60 nodelay;

    # --- Pages statiques locales ---
    location = /robots.txt {
        root @@APP_DIR@@/public;
    }
    location = /errors/50x.html {
        internal;
        root @@APP_DIR@@/public;
    }
    # Seuls 502/504 (backend injoignable / trop lent) sont remplacés par notre page.
    # Le 503 « mode maintenance » est généré par l'application elle-même : on le laisse passer.
    error_page 502 504 /errors/50x.html;
    # Intercepte aussi les 502/504 renvoyés par le nginx du backend (gunicorn arrêté).
    # Seuls les codes listés ci-dessus sont concernés : 500/503 de Django passent tels quels.
    proxy_intercept_errors on;

    # --- Fichiers statiques : mis en cache sur le portail ---
    location /static/ {
        proxy_pass http://bwana_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache bwana_static;
        proxy_cache_valid 200 10m;
        proxy_cache_use_stale error timeout updating http_502 http_503 http_504;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Cache-Status $upstream_cache_status;
        expires 1h;
    }

    # --- Pages de connexion / administration : anti brute-force ---
    location ~ ^/BwanaFacturation/(users/connexion|masque-zone-ad-rouge)/ {
        limit_req zone=bwana_login burst=15 nodelay;
        proxy_pass http://bwana_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_send_timeout    120s;
        proxy_read_timeout    120s;
        proxy_redirect off;
    }

    # --- Tout le reste (dont /media/, protégé par login Django) → backend ---
    location / {
        proxy_pass http://bwana_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_send_timeout    120s;
        proxy_read_timeout    120s;
        proxy_redirect off;
    }
}
SITE_EOF
render "/etc/nginx/sites-available/${SITE}"
nginx -t
systemctl reload nginx

cat > /etc/logrotate.d/${SITE} <<LR_EOF
${APP_DIR}/logs/*.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        [ -s /run/nginx.pid ] && kill -USR1 \$(cat /run/nginx.pid) || true
    endscript
}
LR_EOF

# ------------------------------- 8. PARE-FEU ---------------------------------
log "8/8 Pare-feu (ufw)…"
SSH_PORT="$(sshd -T 2>/dev/null | awk '/^port /{print $2; exit}')"; SSH_PORT="${SSH_PORT:-22}"
if [[ "${ENABLE_UFW}" == "yes" ]]; then
    ufw allow "${SSH_PORT}/tcp" comment 'SSH' >/dev/null
    ufw allow 80/tcp  comment 'HTTP'  >/dev/null
    ufw allow 443/tcp comment 'HTTPS' >/dev/null
    ufw status | grep -q "Status: active" || ufw --force enable >/dev/null
    ok "ufw actif : SSH(${SSH_PORT}), 80, 443."
else
    warn "ENABLE_UFW=no : pare-feu non modifié."
fi

# ------------------------------- VÉRIFICATION --------------------------------
log "Vérification finale…"
sleep 1
H_HTTP="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -m 10 "http://${DOMAIN}/BwanaFacturation/" --resolve "${DOMAIN}:80:127.0.0.1" || true)"
H_LOGIN="$(curl -s -o /dev/null -w '%{http_code}' -m 20 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/BwanaFacturation/users/connexion/" || true)"
H_STATIC="$(curl -s -o /dev/null -w '%{http_code}' -m 20 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/static/img/logo.png" || true)"
H_ROOT="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -m 20 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/" || true)"
echo "   HTTP  /                      → ${H_HTTP}"
echo "   HTTPS /                      → ${H_ROOT}"
echo "   HTTPS /…/users/connexion/    → ${H_LOGIN}"
echo "   HTTPS /static/img/logo.png   → ${H_STATIC}"
[[ "${H_LOGIN}" == "200" ]] || die "Page de connexion en HTTPS : HTTP ${H_LOGIN} (attendu 200). Voir ${APP_DIR}/logs/error.log"
[[ "${H_STATIC}" == "200" ]] || warn "logo.png : HTTP ${H_STATIC} (attendu 200)."
certbot renew --dry-run >/dev/null 2>&1 && ok "Renouvellement automatique du certificat : OK (test à blanc réussi)." \
    || warn "Test de renouvellement échoué — à vérifier : certbot renew --dry-run"

echo
ok "PORTAIL PUBLIC OPÉRATIONNEL → https://${DOMAIN}/"
cat <<EOF

  Portail   : ${APP_DIR}   (public/, logs/)
  Backend   : http://${BACKEND_IP}:${BACKEND_PORT}
  Logs      : tail -f ${APP_DIR}/logs/access.log ${APP_DIR}/logs/error.log
  Certificat: renouvelé automatiquement par certbot (timer systemd)
EOF
