#!/bin/bash
ID=$(xmllint metainfo.xml --noout --xpath "/component/id/text()")
NAME=$(xmllint metainfo.xml --noout --xpath "/component/name/text()")
BINARY=$(xmllint metainfo.xml --noout --xpath "//binary/text()")
COMMENT=$(xmllint metainfo.xml --noout --xpath "//summary/text()")
CATEGORIES=$(xmllint metainfo.xml --noout --xpath "//category/text()" | paste -sd ";" -)
KEYWORDS=$(xmllint metainfo.xml --noout --xpath "//keyword/text()" | paste -sd ";" -)
PYTHON=$(ls /usr/lib/ | grep python)
DESKTOP="[Desktop Entry]\nType=Application\nName=$NAME\nComment=$COMMENT\nIcon=$ID\nExec=$BINARY"
if [[ "$(xmllint metainfo.xml --noout --xpath "//mediatype/text()")" != "" ]]; then
    DESKTOP+=" %U\nMimeType=$(xmllint metainfo.xml --noout --xpath '//mediatype/text()' | paste -sd ';' -)"
fi
DESKTOP+="\nCategories=$CATEGORIES\nKeywords=$KEYWORDS"
echo -e $DESKTOP > $BINARY.desktop
install -D AppUtils/AppUtils.py /app/lib/$PYTHON/site-packages/AppUtils.py
install -Dm755 main.py /app/bin/$BINARY
install -D metainfo.xml /app/share/metainfo/$ID.metainfo.xml
install -D $BINARY.desktop /app/share/applications/$ID.desktop
install -D app.svg /app/share/icons/hicolor/scalable/apps/$ID.svg
install -D app-symbolic.svg /app/share/icons/hicolor/symbolic/apps/$ID-symbolic.svg
for file in *.svg; do
    if [[ "$file" != "app.svg" && "$file" != "app-symbolic.svg" ]]; then
        install -D $file /app/share/$ID/$file
    fi
done
