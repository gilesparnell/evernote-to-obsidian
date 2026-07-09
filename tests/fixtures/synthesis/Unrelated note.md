---
title: "Unrelated note"
source: fixture
---

This note is deliberately unrelated to any topic.
It mentions food and a foothold, so a naive substring check could confuse those
longer words with a shorter three-letter alias — a word-boundary matcher must
reject them because the letters are embedded inside a larger word.
