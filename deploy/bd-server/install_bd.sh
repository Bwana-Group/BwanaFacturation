#!/usr/bin/env bash
# =============================================================================
#  BwanaFacturation — Installation du SERVEUR BD / BACKEND
#  Serveur : srv1894886.hstgr.cloud (2.25.102.16)
#  Chemin  : /var/www/apps/BwanaFacturation
#
#  Ce serveur contient TOUTE l'application :
#     PostgreSQL (local)  +  Django/gunicorn (127.0.0.1:8000)
#     +  nginx interne (port 8080, accessible UNIQUEMENT depuis le serveur web)
#
#  Le script est IDEMPOTENT : on peut le relancer sans rien casser
#  (le .env, le mot de passe BD et la SECRET_KEY existants sont conservés).
#
#  Usage :   sudo bash install_bd.sh
# =============================================================================
set -Eeuo pipefail
trap 'echo -e "\n\033[1;31m[ERREUR]\033[0m ligne $LINENO : la commande « $BASH_COMMAND » a échoué." >&2' ERR

# ----------------------------- PARAMÈTRES ------------------------------------
APP_NAME="BwanaFacturation"
APP_ROOT="/var/www/apps"
APP_DIR="${APP_ROOT}/${APP_NAME}"
REPO_URL="${REPO_URL:-https://github.com/Bwana-Group/BwanaFacturation.git}"
BRANCH="${BRANCH:-main}"

APP_USER="bwana"
SERVICE="bwanafacturation"
DOMAIN="${DOMAIN:-bwanafacturation.bwhub.tech}"

WEB_SERVER_IP="${WEB_SERVER_IP:-2.24.110.102}"    # seul client autorisé du backend
BACKEND_PORT="${BACKEND_PORT:-8080}"               # port nginx interne
GUNICORN_BIND="127.0.0.1:8000"

DB_NAME="${DB_NAME:-bwanafacturation}"
DB_USER="${DB_USER:-bwana_fact}"

CONF_DIR="/etc/${SERVICE}"
BACKUP_DIR="/var/backups/${SERVICE}"
ENABLE_UFW="${ENABLE_UFW:-yes}"                    # yes|no

# Création optionnelle du super-utilisateur (non interactif) :
#   DJANGO_SUPERUSER_USERNAME=admin DJANGO_SUPERUSER_EMAIL=a@b.c \
#   DJANGO_SUPERUSER_PASSWORD='...' sudo -E bash install_bd.sh

# ------------------------------- OUTILS --------------------------------------
log()  { echo -e "\033[1;34m[BD]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[ OK ]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $*"; }
die()  { echo -e "\033[1;31m[FATAL]\033[0m $*" >&2; exit 1; }

as_app()  { runuser -u "${APP_USER}" -- "$@"; }
manage()  { ( cd "${APP_DIR}" && as_app "${APP_DIR}/venv/bin/python" manage.py "$@" ); }
psql_pg() { runuser -u postgres -- psql -v ON_ERROR_STOP=1 -qtAX "$@"; }

[[ $EUID -eq 0 ]] || die "Lancez ce script en root (sudo bash install_bd.sh)."
cd /    # évite les avertissements « could not change directory » des commandes lancées en tant que postgres/bwana
command -v apt-get >/dev/null || die "Ce script supporte Debian/Ubuntu (apt)."

# ------------------------- 1. PAQUETS SYSTÈME --------------------------------
log "1/12 Installation des paquets système…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git nginx postgresql postgresql-contrib python3 python3-venv \
    python3-pip ufw curl ca-certificates openssl logrotate >/dev/null
python3 - <<'PY' || die "Python >= 3.10 requis (Django 5.2)."
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY
ok "Paquets installés (Python $(python3 -V | cut -d' ' -f2), $(nginx -v 2>&1 | cut -d/ -f2))."

# --------------------- 2. UTILISATEUR & ARBORESCENCE -------------------------
log "2/12 Utilisateur système et répertoires…"
if ! id "${APP_USER}" &>/dev/null; then
    useradd --system --create-home --home-dir "/var/lib/${APP_USER}" \
            --shell /usr/sbin/nologin "${APP_USER}"
fi
mkdir -p "${APP_ROOT}" "${CONF_DIR}" "${BACKUP_DIR}"
chmod 755 "${APP_ROOT}"
chmod 700 "${BACKUP_DIR}"
ok "Utilisateur « ${APP_USER} » prêt."

# ---------------------------- 3. CODE SOURCE ---------------------------------
log "3/12 Récupération du code (${REPO_URL} @ ${BRANCH})…"
mkdir -p "${APP_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 755 "${APP_DIR}"
if [[ -d "${APP_DIR}/.git" ]]; then
    as_app git -C "${APP_DIR}" fetch --quiet origin "${BRANCH}"
    as_app git -C "${APP_DIR}" checkout --quiet "${BRANCH}"
    as_app git -C "${APP_DIR}" merge --ff-only --quiet "origin/${BRANCH}" \
        || warn "Fast-forward impossible : dépôt local divergent, code conservé tel quel."
else
    [[ -z "$(ls -A "${APP_DIR}")" ]] || die "${APP_DIR} n'est pas vide et n'est pas un dépôt git."
    as_app git clone --quiet --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi
COMMIT="$(as_app git -C "${APP_DIR}" rev-parse --short HEAD)"
ok "Code à jour (commit ${COMMIT})."

# Vérification du correctif settings.py (ALLOWED_HOSTS lus depuis l'environnement)
if ! grep -q "SITE_DOMAIN" "${APP_DIR}/config/settings.py"; then
    die "config/settings.py ne contient pas le correctif de production (SITE_DOMAIN).
     Poussez d'abord le correctif fourni (patch/0001-production-settings.patch) sur GitHub,
     sinon Django répondra « 400 Bad Request » pour ${DOMAIN}."
fi

# ----------------------------- 4. POSTGRESQL ---------------------------------
log "4/12 PostgreSQL…"
systemctl enable --now postgresql >/dev/null
for _ in $(seq 1 20); do runuser -u postgres -- pg_isready -q && break; sleep 1; done
runuser -u postgres -- pg_isready -q || die "PostgreSQL ne démarre pas."

ENV_FILE="${APP_DIR}/.env"
if [[ -f "${ENV_FILE}" ]] && grep -q '^DB_PASSWORD=' "${ENV_FILE}"; then
    DB_PASSWORD="$(grep '^DB_PASSWORD=' "${ENV_FILE}" | head -1 | cut -d= -f2-)"
else
    DB_PASSWORD="$(openssl rand -hex 24)"
fi

if [[ "$(psql_pg -c "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'")" != "1" ]]; then
    psql_pg -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}'"
else
    psql_pg -c "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASSWORD}'"
fi
if [[ "$(psql_pg -c "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")" != "1" ]]; then
    psql_pg -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}"
fi
ENC="$(psql_pg -c "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname='${DB_NAME}'")"
[[ "${ENC}" == "UTF8" ]] || die "La base ${DB_NAME} n'est pas en UTF8 (${ENC})."

# PostgreSQL ne doit écouter qu'en local : l'application est sur ce même serveur.
LISTEN="$(psql_pg -c "SHOW listen_addresses")"
if [[ "${LISTEN}" != "localhost" && "${LISTEN}" != "127.0.0.1" ]]; then
    warn "PostgreSQL écoute sur « ${LISTEN} » — il n'est pas nécessaire de l'exposer. Vérifiez le pare-feu."
fi
ok "Base « ${DB_NAME} » (UTF8), rôle « ${DB_USER} », écoute : ${LISTEN}."

# -------------------------------- 5. .ENV ------------------------------------
log "5/12 Fichier d'environnement ${ENV_FILE}…"
if [[ ! -f "${ENV_FILE}" ]]; then
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
    cat > "${ENV_FILE}" <<EOF
# ===== BwanaFacturation — production (généré le $(date -u +%F)) =====
# Ne JAMAIS committer ce fichier. Après modification : systemctl restart ${SERVICE}
DEBUG=False
SECRET_KEY=${SECRET_KEY}

SITE_DOMAIN=${DOMAIN}
SITE_URL=https://${DOMAIN}
ALLOWED_HOSTS=${DOMAIN},127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://${DOMAIN}

DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_HOST=127.0.0.1
DB_PORT=5432

# --- E-mail principal (notifications, validation de compte) : À RENSEIGNER ---
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# --- E-mail dédié aux factures/devis (2e compte) : À RENSEIGNER ---
FACTURE_EMAIL_HOST=smtp.gmail.com
FACTURE_EMAIL_PORT=587
FACTURE_EMAIL_HOST_USER=
FACTURE_EMAIL_HOST_PASSWORD=
FACTURE_DEFAULT_FROM_EMAIL=factures@bwanafacturation.com
EOF
    ok ".env créé avec une SECRET_KEY et un mot de passe BD aléatoires."
else
    ok ".env existant conservé."
fi
chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

# ----------------------- 6. ENVIRONNEMENT PYTHON -----------------------------
log "6/12 Environnement virtuel et dépendances…"
[[ -x "${APP_DIR}/venv/bin/python" ]] || as_app python3 -m venv "${APP_DIR}/venv"

# requirements.txt de l'archive d'origine est en UTF-16 (illisible par pip sous Linux) :
REQ_TMP="$(mktemp)"; chmod 644 "${REQ_TMP}"
python3 - "${APP_DIR}/requirements.txt" "${REQ_TMP}" <<'PY'
import sys
raw = open(sys.argv[1], 'rb').read()
if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
    txt = raw.decode('utf-16')
else:
    txt = raw.decode('utf-8-sig')
txt = txt.replace('\r\n', '\n').replace('\r', '\n')
open(sys.argv[2], 'w', encoding='utf-8', newline='\n').write(txt)
PY
as_app "${APP_DIR}/venv/bin/pip" install --quiet --upgrade pip wheel
as_app "${APP_DIR}/venv/bin/pip" install --quiet -r "${REQ_TMP}"
grep -qi '^gunicorn' "${REQ_TMP}" || as_app "${APP_DIR}/venv/bin/pip" install --quiet "gunicorn==23.0.0"
rm -f "${REQ_TMP}"
ok "Dépendances installées ($(${APP_DIR}/venv/bin/python -c 'import django;print("Django",django.get_version())'))."

# --------------------------- 7. DJANGO (BD + static) -------------------------
log "7/12 Django : contrôle, migrations, fichiers statiques, données initiales…"
mkdir -p "${APP_DIR}/media" "${APP_DIR}/staticfiles"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/media" "${APP_DIR}/staticfiles"

manage check
manage migrate --noinput
manage collectstatic --noinput --verbosity 0

# Données de référence (pays, taxes, provinces) : uniquement sur base vierge.
NB_PAYS="$(manage shell -c "from taxes.models import Pays; print(Pays.objects.count())" | tail -1)"
if [[ "${NB_PAYS}" == "0" ]]; then
    manage loaddata fixtures_all_data.json
    ok "Fixtures chargées (pays, taxes, provinces)."
else
    ok "Données de référence déjà présentes (${NB_PAYS} pays) — fixtures ignorées."
fi

# Super-utilisateur (optionnel, non interactif)
if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
    NB_SU="$(manage shell -c "from django.contrib.auth import get_user_model as g; print(g().objects.filter(is_superuser=True).count())" | tail -1)"
    if [[ "${NB_SU}" == "0" ]]; then
        export DJANGO_SUPERUSER_USERNAME DJANGO_SUPERUSER_PASSWORD
        export DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-admin@${DOMAIN}}"
        manage createsuperuser --noinput \
          || warn "Création du super-utilisateur échouée — faites-le à la main (voir fin du script)."
    fi
fi

# ---------------------------- 8. GUNICORN + SYSTEMD --------------------------
log "8/12 gunicorn + service systemd…"
cat > "${CONF_DIR}/gunicorn.conf.py" <<EOF
import multiprocessing
bind = "${GUNICORN_BIND}"
workers = min(multiprocessing.cpu_count() * 2 + 1, 5)
timeout = 120
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
forwarded_allow_ips = "127.0.0.1"
accesslog = "-"
errorlog = "-"
EOF

cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=BwanaFacturation (gunicorn / Django)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/gunicorn config.wsgi:application -c ${CONF_DIR}/gunicorn.conf.py
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=3
KillMode=mixed
TimeoutStopSec=40
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "${SERVICE}" >/dev/null
systemctl restart "${SERVICE}"
ok "Service ${SERVICE} démarré."

# ------------------------------ 9. NGINX INTERNE -----------------------------
log "9/12 nginx interne (port ${BACKEND_PORT}, réservé à ${WEB_SERVER_IP})…"
cat > "/etc/nginx/sites-available/${SERVICE}-backend" <<'NGINX_EOF'
# BwanaFacturation — backend interne. Accessible uniquement par le serveur web.
map $http_x_forwarded_proto $bwana_proto {
    default $http_x_forwarded_proto;
    ""      https;          # appels directs locaux (healthchecks) : évite la boucle SECURE_SSL_REDIRECT
}

server {
    listen @@BACKEND_PORT@@;
    server_name _;
    server_tokens off;

    allow @@WEB_SERVER_IP@@;
    allow 127.0.0.1;
    deny  all;

    client_max_body_size 10m;

    # Fichiers statiques servis directement (sans passer par Python)
    location /static/ {
        alias @@APP_DIR@@/staticfiles/;
        expires 1h;
        add_header Cache-Control "public";
        access_log off;
    }

    # Le reste (dont /media/, protégé par login Django) → gunicorn
    location / {
        proxy_pass http://@@GUNICORN_BIND@@;
        proxy_http_version 1.1;
        proxy_set_header Connection        "";
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $bwana_proto;
        proxy_redirect off;
        proxy_connect_timeout 10s;
        proxy_send_timeout    120s;
        proxy_read_timeout    120s;
    }
}
NGINX_EOF
sed -i \
    -e "s|@@BACKEND_PORT@@|${BACKEND_PORT}|g" \
    -e "s|@@WEB_SERVER_IP@@|${WEB_SERVER_IP}|g" \
    -e "s|@@APP_DIR@@|${APP_DIR}|g" \
    -e "s|@@GUNICORN_BIND@@|${GUNICORN_BIND}|g" \
    "/etc/nginx/sites-available/${SERVICE}-backend"
ln -sf "/etc/nginx/sites-available/${SERVICE}-backend" "/etc/nginx/sites-enabled/${SERVICE}-backend"
rm -f /etc/nginx/sites-enabled/default      # page nginx par défaut inutile (aucune autre appli ici)
nginx -t
systemctl enable nginx >/dev/null
systemctl reload nginx 2>/dev/null || systemctl restart nginx
ok "nginx configuré."

# ------------------------------ 10. PARE-FEU ---------------------------------
log "10/12 Pare-feu (ufw)…"
SSH_PORT="$(sshd -T 2>/dev/null | awk '/^port /{print $2; exit}')"; SSH_PORT="${SSH_PORT:-22}"
if [[ "${ENABLE_UFW}" == "yes" ]]; then
    ufw allow "${SSH_PORT}/tcp" comment 'SSH' >/dev/null
    ufw allow from "${WEB_SERVER_IP}" to any port "${BACKEND_PORT}" proto tcp comment 'BwanaFacturation web->backend' >/dev/null
    ufw status | grep -q "Status: active" || ufw --force enable >/dev/null
    ok "ufw actif : SSH(${SSH_PORT}) + ${WEB_SERVER_IP}→${BACKEND_PORT}. Tout le reste est fermé."
else
    warn "ENABLE_UFW=no : pare-feu non modifié. Seule la liste d'accès nginx protège le port ${BACKEND_PORT}."
fi

# ------------------------------ 11. SAUVEGARDES ------------------------------
log "11/12 Sauvegardes quotidiennes…"
cat > /usr/local/sbin/bwana-backup <<EOF
#!/usr/bin/env bash
# Sauvegarde BwanaFacturation : base PostgreSQL + fichiers media. Rétention : 14 jours.
set -Eeuo pipefail
cd /
D="${BACKUP_DIR}"; TS="\$(date +%Y%m%d-%H%M%S)"
umask 077
runuser -u postgres -- pg_dump -Fc "${DB_NAME}" > "\${D}/db-\${TS}.dump"
tar -czf "\${D}/media-\${TS}.tar.gz" -C "${APP_DIR}" media
find "\${D}" -type f \( -name 'db-*.dump' -o -name 'media-*.tar.gz' \) -mtime +14 -delete
echo "Sauvegarde OK : \${D}/db-\${TS}.dump"
EOF
chmod 750 /usr/local/sbin/bwana-backup
echo "30 2 * * * root /usr/local/sbin/bwana-backup >> /var/log/bwana-backup.log 2>&1" > /etc/cron.d/${SERVICE}-backup
chmod 644 /etc/cron.d/${SERVICE}-backup
/usr/local/sbin/bwana-backup

# ------------------------------ 12. MISE À JOUR ------------------------------
log "12/12 Commande de mise à jour (bwana-update)…"
cat > /usr/local/sbin/bwana-update <<EOF
#!/usr/bin/env bash
# Met à jour BwanaFacturation depuis GitHub (branche ${BRANCH}) avec retour arrière automatique du code.
set -Eeuo pipefail
cd /
exec 9>/var/lock/bwana-update.lock; flock -n 9 || { echo "Une mise à jour est déjà en cours."; exit 1; }
APP="${APP_DIR}"; U="${APP_USER}"
run() { runuser -u "\${U}" -- "\$@"; }
manage() { ( cd "\${APP}" && run "\${APP}/venv/bin/python" manage.py "\$@" ); }
health() { for _ in \$(seq 1 20); do
    c=\$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: ${DOMAIN}' -H 'X-Forwarded-Proto: https' http://127.0.0.1:${BACKEND_PORT}/BwanaFacturation/users/connexion/ || true)
    [[ "\$c" == "200" ]] && return 0; sleep 1; done; return 1; }

OLD=\$(run git -C "\${APP}" rev-parse HEAD)
/usr/local/sbin/bwana-backup
run git -C "\${APP}" fetch --quiet origin ${BRANCH}
NEW=\$(run git -C "\${APP}" rev-parse origin/${BRANCH})
[[ "\${OLD}" == "\${NEW}" ]] && echo "Déjà à jour (\${OLD:0:7})." && exit 0
echo "Mise à jour \${OLD:0:7} → \${NEW:0:7}"
run git -C "\${APP}" merge --ff-only "origin/${BRANCH}"

rollback() { echo "ÉCHEC — retour au code \${OLD:0:7}"; run git -C "\${APP}" reset --hard "\${OLD}"
    run "\${APP}/venv/bin/pip" install --quiet -r "\${APP}/requirements.txt" || true
    systemctl restart ${SERVICE}; echo "Code restauré. NB : les migrations BD éventuelles ne sont pas annulées (voir sauvegarde ${BACKUP_DIR})."; exit 1; }
trap rollback ERR

python3 - "\${APP}/requirements.txt" /tmp/bwana-req.txt <<'PY'
import sys
raw=open(sys.argv[1],'rb').read()
t=raw.decode('utf-16') if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else raw.decode('utf-8-sig')
open(sys.argv[2],'w',newline='\n').write(t.replace('\r\n','\n'))
PY
chmod 644 /tmp/bwana-req.txt
run "\${APP}/venv/bin/pip" install --quiet -r /tmp/bwana-req.txt
manage check
manage migrate --noinput
manage collectstatic --noinput --verbosity 0
systemctl restart ${SERVICE}
health
trap - ERR
echo "Mise à jour réussie : \${NEW:0:7}"
EOF
chmod 750 /usr/local/sbin/bwana-update
ok "Utilisez « sudo bwana-update » pour déployer les prochaines versions."

# ------------------------------- VÉRIFICATION --------------------------------
log "Vérification finale…"
sleep 2
HC="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN}" http://127.0.0.1:${BACKEND_PORT}/BwanaFacturation/users/connexion/ || true)"
HS="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN}" http://127.0.0.1:${BACKEND_PORT}/static/img/logo.png || true)"
[[ "${HC}" == "200" ]] || { journalctl -u "${SERVICE}" -n 30 --no-pager; die "Page de connexion : HTTP ${HC} (attendu 200)."; }
[[ "${HS}" == "200" ]] || warn "Fichier statique logo.png : HTTP ${HS} (attendu 200)."
systemctl is-active --quiet "${SERVICE}" && systemctl is-active --quiet nginx && systemctl is-active --quiet postgresql \
    || die "Un des services (gunicorn/nginx/postgresql) n'est pas actif."

echo
ok "BACKEND OPÉRATIONNEL — page de connexion : HTTP ${HC}, static : HTTP ${HS}"
cat <<EOF

  Application : ${APP_DIR}   (commit ${COMMIT})
  Backend     : http://2.25.102.16:${BACKEND_PORT}  (réservé à ${WEB_SERVER_IP})
  Configuration à compléter : ${ENV_FILE}   (e-mails SMTP) puis : systemctl restart ${SERVICE}

  Créer l'administrateur (si pas déjà fait) :
     cd ${APP_DIR} && sudo -u ${APP_USER} ./venv/bin/python manage.py createsuperuser

  Logs        : journalctl -u ${SERVICE} -f
  Mise à jour : sudo bwana-update
  Sauvegarde  : sudo bwana-backup   (auto. chaque nuit à 02h30 → ${BACKUP_DIR})

  PROCHAINE ÉTAPE : lancer install_web.sh sur le serveur web (2.24.110.102).
EOF
