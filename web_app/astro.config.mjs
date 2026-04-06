import { defineConfig } from 'astro/config';
// import sitemap from '@astrojs/sitemap';  // base 경로 이슈로 일시 비활성화

// GitHub Pages 배포 시 repo 이름을 base로 설정
// 예: https://chenghun1234-dotcom.github.io/biz-flow/
export default defineConfig({
  site: 'https://chenghun1234-dotcom.github.io',
  base: '/biz-flow',
  integrations: [],
  output: 'static',
  build: {
    // GitHub Pages에 최적화된 정적 빌드
    assets: '_assets',
  },
});
