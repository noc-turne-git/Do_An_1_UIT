const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// lucide-react-native publishes its ESM icons as .mjs files.
config.resolver.sourceExts = [...new Set([...config.resolver.sourceExts, 'mjs'])];

module.exports = config;
