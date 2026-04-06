import { defineConfig } from 'astro/config';
// import sitemap from '@astrojs/sitemap';  // 추후 활성화 가능

// 커스텀 도메인 설정
export default defineConfig({
  site: 'https://biz-flow.nextfintechai.com',
  base: '/',
  integrations: [],
  output: 'static',
  build: {
    assets: '_assets',
  },
});
