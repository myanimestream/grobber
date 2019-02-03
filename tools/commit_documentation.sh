#!/usr/bin/env bash
set -e

mv docs/build /tmp/
mv .git /tmp/

rm -rf *
# delete hidden files
rm -rf ./.* 2> /dev/null

mv /tmp/build/* .
mv /tmp/.git .

rev=$(git rev-parse --short HEAD)

git config credential.helper "cache --timeout=120"
git config user.email "$GH_EMAIL"
git config user.name "$GH_USERNAME"

git remote add upstream "https://$GH_TOKEN@github.com/$CIRCLE_PROJECT_USERNAME/$CIRCLE_PROJECT_REPONAME.git"
git fetch upstream
git reset upstream/gh-pages

git add --force .
git commit --message "chore: deploy ${rev}"
git push --quiet upstream HEAD:gh-pages > /dev/null 2>&1