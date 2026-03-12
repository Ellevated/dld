// DLD-specific hook overrides.
// Deep-merged over hooks.config.mjs defaults by utils.mjs:loadConfig().
// This file is NOT in the template — it's a DLD project customization.

export default {
  preEdit: {
    excludeFromSync: [
      '.claude/rules/localization.md',
      '.claude/rules/template-sync.md',
      '.claude/CUSTOMIZATIONS.md',
      '.claude/settings.local.json',
    ],
  },
};
