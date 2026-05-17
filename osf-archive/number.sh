#!/bin/zsh
for i in p*s?.vtt; do f=`echo $i | sed 's/\..*$//'`; echo $f; { head -n2 ${f}.vtt & tail -n +3 ${f}.vtt| cat -n | sed -E 's/([[:digit:]]+)	/\1\+/' | sed -E 's/:/\+/' } > ${f}n.csv; done
