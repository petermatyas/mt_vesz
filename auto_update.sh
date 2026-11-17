#!/bin/sh
set -e
# A szkript a saját mappájába lép, így bármelyik felhasználó alatt, bárhová klónozva működik.
cd "$(dirname "$(readlink -f "$0")")"

git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0   # nincs új commit

OLD_REQ=$(git rev-parse HEAD:requirements.txt)
git pull --ff-only -q
NEW_REQ=$(git rev-parse HEAD:requirements.txt)

if [ "$OLD_REQ" != "$NEW_REQ" ]; then
    venv/bin/pip install -q -r requirements.txt
fi

# Cron-módban nincs mit újraindítani: a main.py következő futása már az új kódot használja.
echo "$(date '+%F %T') Frissítve: $(git log -1 --oneline)"