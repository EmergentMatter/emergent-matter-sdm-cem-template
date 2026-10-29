A .sdm built inside the repo no longer records absolute paths in its generator, so it re-emits on any machine; one built outside the repo records the absolute project root and warns.
