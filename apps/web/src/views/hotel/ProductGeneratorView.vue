<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { HotelService, PartnerResource, Room, TravelProduct } from '../../types'

const loading = ref(false)
const loadingData = ref(true)
const rooms = ref<Room[]>([])
const services = ref<HotelService[]>([])
const resources = ref<PartnerResource[]>([])
const products = ref<TravelProduct[]>([])
const selectedIndex = ref(0)
const showAutoResources = ref(false)
const naturalBrief = ref('')
const interpreting = ref(false)
const parsedFields = ref<Array<{ label: string; value: unknown }>>([])

const form = reactive({
  target_date: '',
  weather: 'CLOUDY',
  target_crowd: 'FAMILY',
  minimum_gross_margin: '0.20',
  visitor_budget: '699',
  preferred_price: '599',
  theme: '亲子探索日',
  creative_direction: '',
  variant_count: 3,
  room_inventory_id: 0,
  breakfast_id: 0,
  late_id: 0,
  partner_ids: [] as number[],
})

function supportsCrowd(value: string | undefined, crowd: string) {
  return !value || value === 'ALL' || value.split(/[,，]/).map(item => item.trim()).includes(crowd)
}
function supportsWeather(value: string | undefined, weather: string) {
  return !value || value.split(/[,，]/).map(item => item.trim().toUpperCase()).some(item => item === 'ALL' || item === weather)
}

const eligibleRooms = computed(() => rooms.value.filter(item => item.available_date === form.target_date && item.available_count > 0))
const eligibleServices = computed(() => services.value.filter(item => item.available_date === form.target_date && item.available_quantity > 0 && supportsCrowd(item.suitable_crowds, form.target_crowd)))
function resourcesFor(weather: string) {
  return resources.value.filter(item =>
    item.source_type !== 'PUBLIC_REFERENCE' &&
    item.package_enabled &&
    item.status === 'AVAILABLE' &&
    item.available_date === form.target_date &&
    item.remaining_capacity > 0 &&
    supportsCrowd(item.suitable_crowds, form.target_crowd) &&
    supportsWeather(item.weather_tags, weather),
  )
}
const candidateResources = computed(() => resourcesFor(form.weather))
const selectedRoom = computed(() => rooms.value.find(item => item.id === form.room_inventory_id))
const selectedPartners = computed(() => resources.value.filter(item => form.partner_ids.includes(item.id)))
const partySize = computed(() => ({ FAMILY: 3, COUPLE: 2, FRIENDS: 3, SOLO: 1, LOCAL_WEEKEND: 2 }[form.target_crowd] || 2))
const inventorySummary = computed(() => ({
  rooms: eligibleRooms.value.length,
  services: eligibleServices.value.length,
  experiences: candidateResources.value.length,
}))

function chooseWeather() {
  const choices = ['CLOUDY', 'SUNNY', 'RAIN']
  return choices
    .map(weather => ({ weather, count: resourcesFor(weather).length }))
    .sort((left, right) => right.count - left.count || choices.indexOf(left.weather) - choices.indexOf(right.weather))[0]?.weather || 'CLOUDY'
}

function syncSmartInventory() {
  if (!form.target_date) return
  form.weather = chooseWeather()
  const sortedRooms = [...eligibleRooms.value].sort((left, right) => right.available_count - left.available_count)
  const room = sortedRooms[0]
  form.room_inventory_id = room?.id || 0
  const breakfast = eligibleServices.value.filter(item => item.service_type === 'BREAKFAST').sort((left, right) => right.available_quantity - left.available_quantity)[0]
  const late = eligibleServices.value.filter(item => item.service_type === 'LATE_CHECKOUT').sort((left, right) => right.available_quantity - left.available_quantity)[0]
  form.breakfast_id = breakfast?.id || 0
  form.late_id = late?.id || 0
  form.partner_ids = [...candidateResources.value]
    .sort((left, right) => right.remaining_capacity - left.remaining_capacity)
    .slice(0, 4)
    .map(item => item.id)
}

async function loadData() {
  loadingData.value = true
  try {
    const [roomResponse, serviceResponse, resourceResponse] = await Promise.all([hotelApi.rooms(), hotelApi.services(), hotelApi.resources()])
    rooms.value = roomResponse.data
    services.value = serviceResponse.data
    resources.value = resourceResponse.data
    const preferredRoom = [...rooms.value].sort((left, right) => right.available_count - left.available_count)[0]
    form.target_date = preferredRoom?.available_date || ''
    syncSmartInventory()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loadingData.value = false
  }
}

async function interpretBrief() {
  if (!naturalBrief.value.trim()) { ElMessage.warning('先写一句这次想做什么，例如“周末带孩子看展，预算900，想要室内一些”'); return }
  interpreting.value = true
  try {
    const response = await hotelApi.interpretProductDraft(naturalBrief.value.trim())
    const interpreted = response.data.interpreted || {}
    const editableFields = ['target_date', 'weather', 'target_crowd', 'theme', 'visitor_budget', 'preferred_price', 'variant_count', 'creative_direction']
    editableFields.forEach((field) => { if (interpreted[field] !== undefined) (form as Record<string, unknown>)[field] = interpreted[field] })
    parsedFields.value = (response.data.parsed_fields || []).map((item) => ({ label: String(item.label), value: item.value }))
    syncSmartInventory()
    ElMessage.success('已解析需求，下面仍可手动调整')
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { interpreting.value = false }
}

function choose(index: number) { selectedIndex.value = index }
function setPersona(crowd: string, theme: string) {
  form.target_crowd = crowd
  form.theme = theme
  syncSmartInventory()
}
function systemSelections() {
  const quantity = partySize.value
  return [
    form.breakfast_id ? { resource_type: 'HOTEL_SERVICE', resource_id: form.breakfast_id, quantity_per_package: quantity } : null,
    form.late_id ? { resource_type: 'HOTEL_SERVICE', resource_id: form.late_id, quantity_per_package: 1 } : null,
    ...form.partner_ids.map(resource_id => ({ resource_type: 'PARTNER_RESOURCE', resource_id, quantity_per_package: quantity })),
  ].filter(Boolean)
}
async function generate() {
  syncSmartInventory()
  if (!form.room_inventory_id || !form.partner_ids.length) {
    ElMessage.warning('当前日期下可组合的房间或体验不足，请换一个日期或客群再试。')
    return
  }
  loading.value = true
  products.value = []
  selectedIndex.value = 0
  try {
    const response = await hotelApi.generateProduct({
      target_date: form.target_date,
      weather: form.weather,
      target_crowd: form.target_crowd,
      minimum_gross_margin: form.minimum_gross_margin,
      visitor_budget: form.visitor_budget,
      preferred_price: form.preferred_price,
      theme: form.theme,
      creative_direction: form.creative_direction,
      variant_count: form.variant_count,
      room_inventory_id: form.room_inventory_id,
      resource_selections: systemSelections(),
    })
    products.value = response.data.products?.length ? response.data.products : [response.data.product]
    ElMessage.success('已按真实库存生成 ' + products.value.length + ' 套可选方案')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}
async function publish() {
  if (!product.value) return
  try {
    products.value[selectedIndex.value] = (await hotelApi.productStatus(product.value.id, 'ON_SALE')).data
    ElMessage.success('已发布当前方案')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}
const product = computed(() => products.value[selectedIndex.value] || null)
watch([() => form.target_date, () => form.target_crowd], () => {
  products.value = []
  syncSmartInventory()
})
onMounted(loadData)
</script>

<template>
  <div class="studio-head">
    <div class="studio-head__copy">
      <div class="eyebrow">智能组包</div>
      <h1>留一点选择，剩下交给真实库存</h1>
      <p>选好日期、同行的人和想要的感觉，系统会自动筛选可用房间与体验，生成几套不同风格的杭州周末方案。</p>
    </div>
    <div class="studio-orb" aria-hidden="true"><i /> <span>杭</span></div>
    <el-button plain class="studio-refresh" @click="loadData">更新可用资源</el-button>
  </div>

  <div v-if="loadingData" class="panel empty-state">正在读取可用房间与体验…</div>
  <template v-else>
    <section class="brief-panel panel"><div><div class="eyebrow">一句话组包</div><strong>把同行人、日期、预算和偏好交给系统解析</strong><small>解析只会填入可修改的草稿；房间与体验仍按当前库存自动匹配。</small></div><el-input v-model="naturalBrief" placeholder="例如：周末两个人看展吃饭，预算 1200，想有一点夜游氛围" @keyup.enter="interpretBrief" /><el-button type="primary" :loading="interpreting" @click="interpretBrief">解析</el-button><div v-if="parsedFields.length" class="brief-chips"><span v-for="item in parsedFields" :key="item.label">{{ item.label }}：{{ item.value }}</span></div></section>
    <div class="studio-persona-quick">
      <span>这次想和谁出发？</span>
      <button :class="{ active: form.target_crowd === 'FAMILY' }" @click="setPersona('FAMILY', '亲子探索日')">亲子家庭</button>
      <button :class="{ active: form.target_crowd === 'COUPLE' }" @click="setPersona('COUPLE', '湖边约会')">两人约会</button>
      <button :class="{ active: form.target_crowd === 'FRIENDS' }" @click="setPersona('FRIENDS', '城市玩乐')">朋友相聚</button>
      <button :class="{ active: form.target_crowd === 'SOLO' }" @click="setPersona('SOLO', '一个人的咖啡漫游')">一个人慢游</button>
      <button :class="{ active: form.target_crowd === 'LOCAL_WEEKEND' }" @click="setPersona('LOCAL_WEEKEND', '周末夜游')">本地周末</button>
    </div>

    <div class="smart-stats">
      <div><small>可用房型</small><strong>{{ inventorySummary.rooms }}</strong><span>系统优先安排余量充足的房间</span></div>
      <div><small>酒店服务</small><strong>{{ inventorySummary.services }}</strong><span>自动匹配早餐、延迟退房等服务</span></div>
      <div><small>备选体验</small><strong>{{ inventorySummary.experiences }}</strong><span>每套方案会从中选择合适组合</span></div>
      <div class="smart-stats__note"><i /> 已按日期与客群筛选<br /><span>天气只用于保障体验可执行</span></div>
    </div>

    <div class="studio-layout">
      <section class="panel smart-form">
        <div class="section-title smart-form__heading">
          <div><div class="eyebrow">三步开始</div><h2>告诉系统你想要什么</h2></div>
          <span>不用手动挑库存</span>
        </div>
        <el-form label-position="top">
          <div class="form-grid compact-form">
            <el-form-item label="入住日期">
              <el-date-picker v-model="form.target_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
            <el-form-item label="参考售价">
              <el-input v-model="form.preferred_price"><template #prepend>¥</template></el-input>
            </el-form-item>
            <el-form-item label="同行的人">
              <el-select v-model="form.target_crowd" style="width:100%">
                <el-option label="亲子家庭" value="FAMILY" />
                <el-option label="两人约会" value="COUPLE" />
                <el-option label="朋友相聚" value="FRIENDS" />
                <el-option label="一个人慢游" value="SOLO" />
                <el-option label="本地周末" value="LOCAL_WEEKEND" />
              </el-select>
            </el-form-item>
            <div class="auto-variant"><span>候选方案</span><strong>自动生成 {{ form.variant_count }} 套</strong><small>根据可用库存给出不同搭配</small></div>
            <el-form-item class="full" label="这次想怎么玩">
              <el-input v-model="form.theme" placeholder="如：看展以后去吃一顿好饭、带孩子探索城市、朋友们夜游放松" />
            </el-form-item>
            <el-form-item class="full" label="想要的感觉（可选）">
              <el-input v-model="form.creative_direction" placeholder="如：轻松一点、适合拍照、有故事感、适合发短视频" />
            </el-form-item>
          </div>
          <el-button type="primary" size="large" class="generate-button" :loading="loading" @click="generate">生成我的杭州周末方案</el-button>
        </el-form>

        <div class="auto-picks">
          <div class="auto-picks__head"><div><b>系统已准备好这些内容</b><span>每套按 {{ partySize }} 人出行自动计算</span></div><button @click="showAutoResources = !showAutoResources">{{ showAutoResources ? '收起' : '查看' }}</button></div>
          <div class="auto-picks__main">
            <span>{{ selectedRoom?.room_type || '等待可用房间' }}</span>
            <i>＋</i>
            <span>{{ selectedPartners.length }} 个备选体验</span>
            <i>＋</i>
            <span>{{ form.breakfast_id || form.late_id ? '贴心酒店服务' : '基础住宿' }}</span>
          </div>
          <div v-if="showAutoResources" class="auto-picks__detail">
            <div v-if="selectedRoom"><small>住宿</small><strong>{{ selectedRoom.room_type }} · 余 {{ selectedRoom.available_count }} 间</strong></div>
            <div v-for="item in selectedPartners" :key="item.id"><small>体验</small><strong>{{ item.resource_name }} · 余 {{ item.remaining_capacity }} 个名额</strong></div>
          </div>
        </div>
      </section>

      <section class="panel candidate-stage">
        <div v-if="!products.length" class="candidate-empty">
          <div class="candidate-empty__visual"><span>✦</span><i /><b>杭州周末</b></div>
          <h2>先给一个方向，再看不同的答案</h2>
          <p>系统会从当前真实库存中自动搭配房间、服务和体验。生成后，你可以挑选最适合发布的一套。</p>
        </div>
        <template v-else>
          <div class="candidate-stage__head"><div><div class="eyebrow">候选方案</div><h2>挑一套最想让客人出发的</h2></div><span>{{ products.length }} 套可选</span></div>
          <div class="candidate-tabs">
            <button v-for="(item, index) in products" :key="item.id" :class="{ active: selectedIndex === index }" @click="choose(index)">
              <small>方案 {{ index + 1 }}</small><strong>{{ item.product_name }}</strong><span>{{ item.theme }} · ¥{{ item.suggested_price }}</span>
            </button>
          </div>
          <div v-if="product" class="candidate-detail">
            <div class="candidate-detail__top"><span>{{ product.theme }}</span><StatusTag :status="product.status" /></div>
            <h2>{{ product.product_name }}</h2>
            <p>{{ product.recommendation_reason }}</p>
            <div class="candidate-chips"><span v-for="item in product.resources" :key="item.id">{{ item.resource_name }}</span></div>
            <div class="candidate-price"><div><small>参考售价</small><strong>¥{{ product.suggested_price }}</strong></div><div><small>可售数量</small><strong>{{ product.sale_quantity }} 套</strong></div><button @click="$router.push('/hotel/products/' + product.id)">查看完整内容与宣传素材 →</button></div>
            <el-alert v-if="product.risk_message" :title="product.risk_message" type="info" :closable="false" show-icon />
            <div class="form-actions"><el-button @click="$router.push('/hotel/products/' + product.id)">查看详情</el-button><el-button type="primary" :disabled="product.status !== 'DRAFT'" @click="publish">发布当前方案</el-button></div>
          </div>
        </template>
      </section>
    </div>
  </template>
</template>

<style scoped>
.studio-head{position:relative;display:flex;align-items:center;gap:22px;overflow:hidden;padding:34px 36px;border:1px solid #e2e9e5;border-radius:22px;background:linear-gradient(125deg,#fff 6%,#f3f8f5 66%,#faf4e9);box-shadow:0 16px 38px rgba(23,63,56,.06)}
.studio-head__copy{position:relative;z-index:1;max-width:720px}.studio-head h1{margin:8px 0 10px;font:500 clamp(29px,3.4vw,42px)/1.16 Georgia,'Songti SC',serif;letter-spacing:-.7px}.studio-head p{margin:0;color:var(--muted);font-size:14px;line-height:1.8}.studio-orb{position:absolute;right:126px;top:-75px;width:250px;height:250px;border-radius:50%;background:radial-gradient(circle at 35% 32%,#fbdf9d,#e3b66d 34%,#30695e 36%,#173f39 68%);box-shadow:inset 0 0 0 18px rgba(255,255,255,.16);animation:float-orb 7s ease-in-out infinite}.studio-orb span{position:absolute;right:41px;bottom:34px;color:#fff;font:700 74px Georgia,serif;opacity:.86}.studio-orb i{position:absolute;inset:22px;border:1px solid rgba(255,255,255,.35);border-radius:50%}.studio-refresh{position:absolute;right:28px;bottom:24px;z-index:1}.studio-persona-quick{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:18px 0 14px;padding:13px 16px;border:1px solid var(--line);border-radius:14px;background:#fff}.studio-persona-quick>span{margin-right:5px;color:var(--ink);font-size:13px;font-weight:700}.studio-persona-quick button{border:1px solid #dce9e2;border-radius:999px;background:#f8fbf9;color:#5b736d;padding:8px 13px;font-size:12px;transition:.2s}.studio-persona-quick button:hover,.studio-persona-quick button.active{border-color:var(--teal);background:var(--teal);color:#fff;transform:translateY(-1px)}.smart-stats{display:grid;grid-template-columns:repeat(4,1fr);overflow:hidden;margin-bottom:20px;border:1px solid #e2ebe6;border-radius:16px;background:#fff}.smart-stats>div{min-height:92px;padding:17px 20px;border-right:1px solid #edf1ee}.smart-stats>div:last-child{border-right:0}.smart-stats small,.smart-stats span{display:block;color:var(--muted);font-size:11px}.smart-stats strong{display:inline-block;margin:5px 7px 2px 0;color:var(--teal-dark);font:28px Georgia,serif}.smart-stats__note{display:flex;align-items:center;color:#496a60;font-size:13px;line-height:1.6;background:#fafcfb}.smart-stats__note i{width:8px;height:8px;margin-right:9px;border-radius:50%;background:#65ac8b;box-shadow:0 0 0 5px #e7f4ed}.studio-layout{display:grid;grid-template-columns:minmax(310px,.78fr) minmax(0,1.22fr);gap:20px;align-items:start}.smart-form{padding:23px}.smart-form__heading{margin:0 0 18px}.smart-form__heading h2{margin-top:5px;font-size:20px}.compact-form{gap:12px}.smart-form :deep(.el-form-item){margin-bottom:12px}.smart-form :deep(.el-form-item__label){padding-bottom:5px;font-size:13px;font-weight:650;line-height:1.3}.generate-button{width:100%;margin-top:4px;height:44px;font-size:14px}.auto-picks{margin-top:18px;padding:15px;border:1px solid #e2ece6;border-radius:14px;background:#f8fbf9}.auto-picks__head{display:flex;justify-content:space-between;gap:10px;align-items:start}.auto-picks__head b{display:block;font-size:13px}.auto-picks__head span{display:block;margin-top:3px;color:var(--muted);font-size:11px}.auto-picks__head button{border:0;background:none;color:var(--teal);font-size:12px}.auto-picks__main{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-top:13px}.auto-picks__main span{padding:6px 8px;border-radius:8px;background:#fff;color:#44665c;font-size:11px}.auto-picks__main i{font-style:normal;color:#95b8ab}.auto-picks__detail{display:grid;gap:6px;margin-top:12px;padding-top:10px;border-top:1px solid #dfeae4}.auto-picks__detail div{display:flex;justify-content:space-between;gap:9px}.auto-picks__detail small{color:var(--muted);font-size:11px}.auto-picks__detail strong{font-size:11px;text-align:right}.candidate-stage{min-height:560px;padding:25px}.candidate-empty{display:grid;place-items:center;align-content:center;min-height:510px;text-align:center}.candidate-empty__visual{position:relative;width:150px;height:150px;margin-bottom:18px;border-radius:44px;background:linear-gradient(145deg,#e8f3ed,#fff6e7);box-shadow:inset 0 0 0 1px #e3ebe6}.candidate-empty__visual span{position:absolute;left:26px;top:24px;color:#d59c4d;font-size:43px}.candidate-empty__visual i{position:absolute;right:22px;bottom:31px;width:73px;height:73px;border:2px solid #3d8274;border-radius:50%}.candidate-empty__visual b{position:absolute;right:15px;bottom:13px;color:#326659;font:15px Georgia,serif}.candidate-empty h2,.candidate-stage__head h2{margin:4px 0 9px;font:500 26px Georgia,'Songti SC',serif}.candidate-empty p{max-width:400px;margin:0;color:var(--muted);font-size:13px;line-height:1.8}.candidate-stage__head{display:flex;align-items:end;justify-content:space-between;gap:16px}.candidate-stage__head>span{padding:6px 9px;border-radius:999px;background:#edf7f2;color:var(--teal-dark);font-size:11px}.candidate-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:18px 0}.candidate-tabs button{min-height:110px;border:1px solid var(--line);border-radius:12px;background:#fff;padding:13px;text-align:left;color:var(--ink);transition:.2s}.candidate-tabs button:hover,.candidate-tabs button.active{border-color:#78b6a2;background:#f2faf6;box-shadow:0 10px 24px rgba(22,95,80,.09);transform:translateY(-2px)}.candidate-tabs small,.candidate-tabs span{display:block;color:var(--muted);font-size:11px}.candidate-tabs strong{display:block;margin:8px 0 6px;font-size:14px;line-height:1.35}.candidate-detail{padding:20px;border-top:1px solid var(--line)}.candidate-detail__top{display:flex;justify-content:space-between;gap:10px;align-items:center}.candidate-detail__top>span{color:var(--teal);font-size:11px;font-weight:700}.candidate-detail h2{margin:13px 0 8px;font-size:25px;line-height:1.3}.candidate-detail>p{margin:0;color:var(--muted);font-size:14px;line-height:1.8}.candidate-chips{display:flex;flex-wrap:wrap;gap:7px;margin:15px 0}.candidate-chips span{padding:6px 9px;border-radius:999px;background:#f1f7f4;color:#39695b;font-size:11px}.candidate-price{display:flex;align-items:center;gap:23px;margin:18px 0;padding:15px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.candidate-price div{min-width:96px}.candidate-price small{display:block;color:var(--muted);font-size:11px}.candidate-price strong{display:block;margin-top:4px;font:24px Georgia,serif;color:var(--teal-dark)}.candidate-price button{margin-left:auto;border:0;background:none;color:var(--teal);font-size:12px;font-weight:650}.form-actions{margin-top:17px}@media(max-width:1050px){.studio-layout{grid-template-columns:1fr}.candidate-stage{min-height:0}.candidate-empty{min-height:340px}}@media(max-width:780px){.studio-head{padding:25px 22px}.studio-orb{right:-58px;top:-96px;opacity:.5}.studio-refresh{position:static;margin-left:auto;align-self:end}.smart-stats{grid-template-columns:1fr 1fr}.smart-stats>div:nth-child(2){border-right:0}.smart-stats>div:nth-child(-n+2){border-bottom:1px solid #edf1ee}.candidate-tabs{grid-template-columns:1fr}.candidate-tabs button{min-height:0}.candidate-price{gap:13px;flex-wrap:wrap}.candidate-price button{margin-left:0;flex-basis:100%;text-align:left}}@media(max-width:500px){.smart-stats{grid-template-columns:1fr}.smart-stats>div{border-right:0;border-bottom:1px solid #edf1ee}.smart-stats>div:last-child{border-bottom:0}.studio-persona-quick>span{flex-basis:100%}.candidate-stage,.smart-form{padding:18px}}@keyframes float-orb{50%{transform:translateY(10px) rotate(5deg)}}
.brief-panel{display:grid;grid-template-columns:minmax(220px,1fr) minmax(260px,1.4fr) auto;align-items:center;gap:12px;margin:0 0 14px}.brief-panel strong,.brief-panel small{display:block}.brief-panel strong{margin-top:4px;font-size:14px}.brief-panel small{margin-top:3px;color:var(--muted);font-size:10px;line-height:1.5}.brief-chips{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px}.brief-chips span{padding:4px 7px;border:1px solid var(--line);border-radius:6px;background:var(--panel-soft);color:var(--muted);font-size:10px}.auto-variant{display:grid;align-content:center;min-height:72px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel-soft)}.auto-variant span,.auto-variant small{color:var(--muted);font-size:10px}.auto-variant strong{margin:4px 0;color:var(--ink);font-family:var(--font-mono);font-size:13px}.studio-head{padding:24px 28px;border-radius:12px;background:var(--paper);box-shadow:var(--shadow)}.studio-head h1,.candidate-empty h2,.candidate-stage__head h2{font-family:var(--font-sans);font-weight:650}.studio-orb{display:none}.studio-refresh{position:static;margin-left:auto}.studio-persona-quick{margin:14px 0 10px;border-radius:10px;background:var(--paper)}.studio-persona-quick button{border-radius:7px;background:var(--panel-soft);border-color:var(--line);padding:7px 10px}.studio-persona-quick button:hover,.studio-persona-quick button.active{border-color:#65766f;background:#3d4d48}.smart-stats{margin-bottom:14px;border-radius:10px}.smart-stats strong{font-family:var(--font-mono);font-size:22px}.smart-stats__note{background:var(--panel-soft)}.studio-layout{gap:14px}.smart-form,.candidate-stage{padding:18px}.candidate-stage{min-height:500px}.candidate-tabs{grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:7px;margin:13px 0}.candidate-tabs button{min-height:88px;padding:10px;border-radius:8px}.candidate-tabs button:hover,.candidate-tabs button.active{border-color:#9ba8a2;background:var(--panel-soft);box-shadow:none}.candidate-detail{padding:14px 0}.candidate-detail h2{font-size:21px}.candidate-price strong{font-family:var(--font-mono);font-size:20px}.candidate-chips span{border:1px solid var(--line);border-radius:6px;background:var(--panel-soft);color:var(--muted)}@media(max-width:780px){.brief-panel{grid-template-columns:1fr}.brief-panel .el-button{width:100%}.studio-refresh{margin-left:0}.auto-variant{grid-column:1/-1}}
</style>
