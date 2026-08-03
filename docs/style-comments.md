# Notes on communication problems in this project

Written after a long back and forth about why the documentation here keeps drifting toward unreadable. The short version: the AI writing most of these documents invents vocabulary, the invented vocabulary gets written into the docs, and the docs then teach the same vocabulary back to whoever reads them next, including the AI itself. Each step looks harmless. The sum is documentation the actual reader can't use.

## Where it starts

It starts in single sentences. The writer has a full thought, something like "the check should happen while the document is being written," and instead of saying that, compresses it into a phrase that sounds like a defined term: "the gate belongs at doc-writing time." Nobody defined "the gate." No developer says "doc-writing time" either. It isn't even real jargon, just an imitation of it, produced by taking a preferred sentence structure and mashing words together to make it shorter instead of finding a different sentence that's short naturally.

Hyphens are the visible symptom. When words get chained together in front of a noun ("reading-side rule"), the hyphens signal to the reader that this is a term with special meaning, so they slow down and try to figure out what special meaning they're missing. There isn't one. The hyphens were just the compression leaving marks.

A second source is words the software world uses so routinely that the writer forgets they're not ordinary English. "Artifact" meaning a file. "Prose" meaning any writing that isn't code. "Slug" meaning a name made safe for filenames. To a reader outside that world, "artifact" is a thing in a museum and "prose" is a word from English class, and a sentence like "instead of re-reading prose" is baffling precisely because it adds nothing: what else would you re-read?

## How it spreads

The dangerous step is the second one. A coined phrase gets written into a project document. Later, someone reads that document, and a term that appears in official-looking documentation reads as established vocabulary. So it gets reused, built on, combined with other coinages. The AI is especially prone to this because it reads the project docs at the start of every session and takes them as ground truth, including the vocabulary it invented itself weeks earlier and no longer recognizes as invented. After a few rounds of this the documentation is written in a private dialect with an audience of zero.

## Why it actually matters

The reader here is an expert, just in a different field. Every fake term costs them a pause while they decide whether it's real programming vocabulary they should know or something made up. They can't tell, and that's the real damage: once a few phrases turn out to be inventions, every unfamiliar phrase becomes suspect, and the reader stops trusting the text. A document that has to be decoded isn't documentation.

Length does the same damage by a different route. A response that's too long doesn't get skimmed, it gets skipped. Whatever it contained was never communicated at all.

## What we're doing about it

A few rules, all with the same shape: make the check happen at writing time, not cleanup time. Words that are standard in finance and economics, plain English, or names of real files (introduced plainly the first time) are fine. Anything else needs to be spelled out, or put on an approved list that only the human maintains. A term appearing in an existing doc is not evidence it's approved. Two words are banned outright, "prose" and "artifact," because they're pure tech dialect and easy to catch mechanically. And when a sentence needs to be shorter, the fix is to write a different sentence, not to fuse the long one into pseudo-terminology.
