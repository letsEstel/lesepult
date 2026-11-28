#!/usr/bin/env bash
# Download the open data the dictionary is built from into $1 (default: dictsrc/). Each source tries a few
# mirrors / file names; a source that cannot be fetched is left out and the build goes on without it.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
D=${1:-dictsrc}; mkdir -p "$D"; cd "$D"
src='{}'
note(){ src=$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); d[sys.argv[2]]=sys.argv[3]; print(json.dumps(d))' "$src" "$1" "$2"); }
get(){ # get OUT URL... — the first URL that works
  local out=$1; shift
  for u in "$@"; do
    echo "↓ $u"
    if curl -fsSL --retry 3 --retry-delay 5 -o "$out.part" "$u"; then mv "$out.part" "$out"; echo "  ✓ $(du -h "$out" | cut -f1)"; echo "$u"; return 0; fi
  done
  rm -f "$out.part"; return 1
}

# Wiktionary (English edition), German entries, extracted by wiktextract
if u=$(get kaikki.jsonl \
    https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl \
    https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.json | tail -1); then note wiktionary "$u"
elif u=$(get kaikki.jsonl.gz https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl.gz | tail -1); then note wiktionary "$u"
fi

# English entries of English Wiktionary, streamed: only their German translation tables are kept (for English → German)
for u in https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl; do
  echo "↓ $u (streamed)"
  if curl -fsSL --retry 3 --retry-delay 5 "$u" | python3 "$HERE/extract_en.py" > en-de.tsv.part && [ -s en-de.tsv.part ]; then
    mv en-de.tsv.part en-de.tsv; echo "  ✓ $(wc -l < en-de.tsv) lines"; note en_translations "$u"; break
  fi
  rm -f en-de.tsv.part
done

# Tatoeba
T=https://downloads.tatoeba.org/exports/per_language
if get deu_sentences.tsv.bz2 $T/deu/deu_sentences.tsv.bz2 >/dev/null && get eng_sentences.tsv.bz2 $T/eng/eng_sentences.tsv.bz2 >/dev/null; then
  bunzip2 -f deu_sentences.tsv.bz2 eng_sentences.tsv.bz2
  if get deu-eng_links.tsv.bz2 $T/deu/deu-eng_links.tsv.bz2 >/dev/null; then bunzip2 -f deu-eng_links.tsv.bz2
  elif get links.tar.bz2 https://downloads.tatoeba.org/exports/links.tar.bz2 >/dev/null; then
    tar -xjf links.tar.bz2 && python3 - <<'EOF'
de={l.split('\t')[0] for l in open('deu_sentences.tsv',encoding='utf8')}
en={l.split('\t')[0] for l in open('eng_sentences.tsv',encoding='utf8')}
with open('deu-eng_links.tsv','w') as o:
    for l in open('links.csv'):
        a=l.split('\t')
        if len(a)>=2 and a[0] in de and a[1].strip() in en: o.write(a[0]+'\t'+a[1].strip()+'\n')
EOF
    rm -f links.tar.bz2 links.csv
  fi
  [ -f deu-eng_links.tsv ] && note tatoeba "https://tatoeba.org"
fi

# Leipzig Corpora Collection, German: the newest news corpus that can be found
for c in deu_news_2024_300K deu_news_2023_300K deu_news_2022_300K deu_news_2024_100K deu_news_2023_100K deu_news_2022_100K deu_news_2021_100K deu_wikipedia_2021_100K deu_mixed-typical_2011_300K; do
  if get leipzig.tar.gz https://downloads.wortschatz-leipzig.de/corpora/$c.tar.gz >/dev/null; then
    tar -xzf leipzig.tar.gz
    s=$(find . -name "*-sentences.txt" | head -1); w=$(find . -name "*-words.txt" | head -1)
    [ -n "$s" ] && mv "$s" leipzig-sentences.txt; [ -n "$w" ] && mv "$w" leipzig-words.txt
    rm -rf leipzig.tar.gz "$c"
    note leipzig "$c"; break
  fi
done
echo "$src" > sources.json
echo "来源：$src"; ls -la
