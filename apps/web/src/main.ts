import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import { Button as VanButton } from 'vant'
import 'element-plus/dist/index.css'
import 'vant/lib/index.css'
import App from './App.vue'
import router from './router'
import './styles/theme.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.use(VanButton)
// Keep page actions in the top bar without Vue Teleport's patch path.
app.directive('toolbar', {
  mounted(el: HTMLElement) { document.getElementById('page-toolbar')?.appendChild(el) },
})
// 等首屏路由解析完再挂载：否则会先渲染一帧「未匹配任何路由」的布局
// （旅居助手会因此先闪一下窄屏再变宽）。
void router.isReady().then(() => app.mount('#app'))
