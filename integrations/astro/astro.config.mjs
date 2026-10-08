import {defineConfig} from 'astro/config';
export default defineConfig({site:'https://astro.localemesh.test', output:'static',
  i18n:{defaultLocale:'en',locales:['en','de'],routing:{prefixDefaultLocale:false}}});
