<script setup lang="ts">
import {
  AlertTriangle,
  CalendarDays,
  Car,
  CircleDollarSign,
  FileDown,
  FileJson,
  Globe2,
  Loader2,
  Map,
  Plus,
  Route,
  Sparkles,
  Trash2
} from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { generateTrip, getDefaultText, parseTripText } from "./api";
import type { GenerateResponse, TripDay } from "./types";

const fallbackText = `我们是两大一小（低于 1.2m），

开电车，电价 1.5 元/度，百公里综合电耗 18 度；
酒店每晚 300 元，
餐费每天 200 元；
景区：韶山景区、黄果树瀑布、小七孔，天眼景区（门票不要钱，摆渡车 50 元一人，保险 10 元一人），凤凰古城免费。
自动查价补充：黄果树瀑布成人票 160 元，观光车 50 元一人，保险 10 元一人；小七孔成人票 120 元，观光车 40 元一人。

D1
合肥 到 岳阳
D2
岳阳 到 韶山
D3
韶山 到 凤凰古城
D4
凤凰古城 到 荔波
D5
荔波 到 小七孔
小七孔 到 中国天眼
中国天眼 到 安顺

D6
安顺 到 黄果树
黄果树 到 贵阳
D7
贵阳市区
D8
贵阳 到 茅台镇红军桥
茅台镇红军桥 到 遵义会议遗址
遵义会议遗址 到 重庆
D9
重庆市区
D10
重庆 回 合肥
`;

const title = ref("自驾行程");
const startDate = ref("2026-07-17");
const mode = ref("estimate");
const exportPdf = ref(false);
const rawText = ref(fallbackText);
const budgetText = ref("");
const days = ref<TripDay[]>([]);
const activeDayIndex = ref(0);
const loading = ref(false);
const status = ref("待解析");
const error = ref("");
const result = ref<GenerateResponse | null>(null);

const dayCount = computed(() => days.value.length);
const legCount = computed(() => days.value.reduce((sum, day) => sum + day.legs.length, 0));
const noteCount = computed(() => days.value.reduce((sum, day) => sum + day.notes.length, 0));
const warnings = computed(() => result.value?.manifest?.warnings || []);
const activeDay = computed(() => days.value[activeDayIndex.value] || null);

function dayRouteTitle(day: TripDay) {
  if (day.legs.length > 0) {
    return [day.legs[0].from, ...day.legs.map((leg) => leg.to)].filter(Boolean).join(" → ");
  }
  if (day.notes.length > 0) {
    return day.notes.join(" / ");
  }
  return "空白行程";
}

async function parseInput() {
  loading.value = true;
  error.value = "";
  result.value = null;
  try {
    const parsed = await parseTripText(rawText.value);
    budgetText.value = parsed.budget_text || "";
    days.value = (parsed.days || []).map((day) => ({
      day: day.day,
      title: day.title,
      legs: day.legs || [],
      notes: day.notes || []
    }));
    activeDayIndex.value = 0;
    status.value = `已解析 ${days.value.length} 天`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "解析失败";
    status.value = "解析失败";
  } finally {
    loading.value = false;
  }
}

function selectDay(index: number) {
  activeDayIndex.value = index;
}

function addDay() {
  days.value.push({ day: `D${days.value.length + 1}`, legs: [], notes: [] });
  activeDayIndex.value = days.value.length - 1;
}

function deleteDay(index: number) {
  days.value.splice(index, 1);
  activeDayIndex.value = Math.min(activeDayIndex.value, Math.max(days.value.length - 1, 0));
}

function addLeg(day: TripDay) {
  day.legs.push({ from: "", to: "" });
}

function addNote(day: TripDay) {
  day.notes.push("");
}

function deleteLeg(day: TripDay, index: number) {
  day.legs.splice(index, 1);
}

function deleteNote(day: TripDay, index: number) {
  day.notes.splice(index, 1);
}

async function generateOutput() {
  loading.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value = await generateTrip({
      title: title.value,
      start_date: startDate.value,
      mode: mode.value,
      budget_text: budgetText.value,
      days: days.value,
      pdf: exportPdf.value
    });
    status.value = "已生成";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "生成失败";
    status.value = "生成失败";
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    const text = await getDefaultText();
    if (text.trim()) {
      rawText.value = text;
    }
  } catch {
    // Fallback text keeps the editor useful when only the static app is opened.
  }
  await parseInput();
});
</script>

<template>
  <div class="min-h-screen">
    <header class="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
      <div class="mx-auto flex w-full max-w-[1440px] items-center justify-between gap-3 px-4 py-3">
        <div class="min-w-0">
          <h1 class="truncate text-xl font-extrabold leading-tight tracking-normal">自驾行程编辑器</h1>
          <div class="mt-1 flex flex-wrap items-center gap-2 text-xs font-semibold text-muted-foreground">
            <span class="ui-icon-text">
              <Car class="ui-icon" aria-hidden="true" />
              <span>本地引擎</span>
            </span>
            <span class="ui-icon-text">
              <Globe2 class="ui-icon" aria-hidden="true" />
              <span>可发布网页</span>
            </span>
            <span class="ui-icon-text">
              <CircleDollarSign class="ui-icon" aria-hidden="true" />
              <span>费用预算</span>
            </span>
          </div>
        </div>
        <div class="ui-action-group shrink-0">
          <button class="ui-button" type="button" :disabled="loading" @click="parseInput">
            <span class="ui-icon-text">
              <Sparkles class="ui-icon" aria-hidden="true" />
              <span>解析</span>
            </span>
          </button>
          <button class="ui-button ui-button-primary" type="button" :disabled="loading || dayCount === 0" @click="generateOutput">
            <span class="ui-icon-text">
              <Loader2 v-if="loading" class="ui-icon animate-spin" aria-hidden="true" />
              <Map v-else class="ui-icon" aria-hidden="true" />
              <span>生成</span>
            </span>
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto grid w-full max-w-[1440px] grid-cols-[minmax(360px,0.72fr)_minmax(430px,1fr)_minmax(300px,0.55fr)] gap-4 px-4 py-4 xl:grid-cols-[minmax(360px,0.75fr)_minmax(480px,1fr)_minmax(320px,0.55fr)] lg:grid-cols-[minmax(360px,0.82fr)_minmax(460px,1.18fr)] max-lg:grid-cols-1">
      <section class="ui-panel overflow-hidden lg:sticky lg:top-[77px]">
        <div class="ui-panel-head">
          <div class="min-w-0">
            <h2 class="text-sm font-extrabold">输入源</h2>
            <p class="mt-0.5 text-xs font-semibold text-muted-foreground">自然语言和 D1/D2 行程</p>
          </div>
        </div>
        <div class="grid gap-3 p-4">
          <div class="grid grid-cols-[minmax(0,1fr)_150px_120px] gap-2 max-sm:grid-cols-1">
            <label class="grid min-w-0 gap-1.5">
              <span class="text-xs font-bold text-muted-foreground">标题</span>
              <input v-model="title" class="ui-input" />
            </label>
            <label class="grid min-w-0 gap-1.5">
              <span class="text-xs font-bold text-muted-foreground">出发日期</span>
              <input v-model="startDate" class="ui-input" type="date" />
            </label>
            <label class="grid min-w-0 gap-1.5">
              <span class="text-xs font-bold text-muted-foreground">模式</span>
              <select v-model="mode" class="ui-input">
                <option value="estimate">estimate</option>
                <option value="auto">auto</option>
                <option value="accurate">accurate</option>
              </select>
            </label>
          </div>
          <textarea
            v-model="rawText"
            class="min-h-[560px] w-full resize-y rounded-lg border border-input bg-white px-3 py-3 font-mono text-[13px] leading-6 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 max-lg:min-h-[360px]"
            spellcheck="false"
          />
        </div>
      </section>

      <section class="ui-panel min-w-0 overflow-hidden">
        <div class="ui-panel-head">
          <div class="min-w-0">
            <h2 class="text-sm font-extrabold">行程卡片</h2>
            <p class="mt-0.5 truncate text-xs font-semibold text-muted-foreground">按天调整路线段和停留点</p>
          </div>
          <button class="ui-button shrink-0" type="button" @click="addDay">
            <span class="ui-icon-text">
              <Plus class="ui-icon" aria-hidden="true" />
              <span>新增一天</span>
            </span>
          </button>
        </div>
        <div class="grid gap-3 p-4">
          <div class="grid grid-cols-3 gap-2">
            <div class="rounded-lg border border-border bg-white p-3">
              <div class="text-xs font-bold text-muted-foreground">天数</div>
              <div class="mt-1 text-2xl font-extrabold text-primary">{{ dayCount }}</div>
            </div>
            <div class="rounded-lg border border-border bg-white p-3">
              <div class="text-xs font-bold text-muted-foreground">路线段</div>
              <div class="mt-1 text-2xl font-extrabold text-primary">{{ legCount }}</div>
            </div>
            <div class="rounded-lg border border-border bg-white p-3">
              <div class="text-xs font-bold text-muted-foreground">停留</div>
              <div class="mt-1 text-2xl font-extrabold text-primary">{{ noteCount }}</div>
            </div>
          </div>

          <div class="grid max-h-[calc(100vh-220px)] gap-2 overflow-auto pr-1 max-lg:max-h-none max-lg:pr-0">
            <button
              v-for="(day, index) in days"
              :key="`${day.day}-${index}`"
              class="grid w-full grid-cols-[64px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg border bg-white p-3 text-left transition hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              :class="index === activeDayIndex ? 'border-primary shadow-sm' : 'border-border'"
              type="button"
              @click="selectDay(index)"
            >
              <span class="rounded-md border border-border bg-muted px-2 py-1 text-center text-sm font-extrabold text-primary">{{ day.day || `D${index + 1}` }}</span>
              <span class="min-w-0">
                <span class="block truncate text-sm font-extrabold">{{ dayRouteTitle(day) }}</span>
                <span class="mt-1 block text-xs font-semibold text-muted-foreground">{{ day.legs.length }} 段 / {{ day.notes.length }} 停留</span>
              </span>
              <Route class="size-4 shrink-0 text-primary" aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      <aside class="ui-panel min-w-0 overflow-hidden lg:sticky lg:top-[77px] lg:col-span-2 xl:col-span-1">
        <div class="ui-panel-head">
          <div class="min-w-0">
            <h2 class="text-sm font-extrabold">编辑与生成</h2>
            <p class="mt-0.5 text-xs font-semibold text-muted-foreground">{{ status }}</p>
          </div>
        </div>
        <div class="grid gap-4 p-4">
          <div v-if="activeDay" class="grid gap-3">
            <div class="grid gap-1.5">
              <span class="text-xs font-bold text-muted-foreground">当前天</span>
              <input v-model="activeDay.day" class="ui-input max-w-[160px] font-extrabold text-primary" />
            </div>

            <div class="grid gap-2">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-sm font-extrabold">路线</h3>
                <button class="ui-button" type="button" @click="addLeg(activeDay)">
                  <span class="ui-icon-text">
                    <Route class="ui-icon" aria-hidden="true" />
                    <span>新增路线</span>
                  </span>
                </button>
              </div>
              <div v-for="(leg, index) in activeDay.legs" :key="`leg-${index}`" class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_36px] gap-2">
                <input v-model="leg.from" class="ui-input" placeholder="出发地" />
                <input v-model="leg.to" class="ui-input" placeholder="目的地" />
                <button class="ui-button ui-button-danger px-2" type="button" aria-label="删除路线" @click="deleteLeg(activeDay, index)">
                  <Trash2 class="ui-icon" aria-hidden="true" />
                </button>
              </div>
            </div>

            <div class="grid gap-2">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-sm font-extrabold">停留</h3>
                <button class="ui-button" type="button" @click="addNote(activeDay)">
                  <span class="ui-icon-text">
                    <Plus class="ui-icon" aria-hidden="true" />
                    <span>新增停留</span>
                  </span>
                </button>
              </div>
              <div v-for="(note, index) in activeDay.notes" :key="`note-${index}`" class="grid grid-cols-[minmax(0,1fr)_36px] gap-2">
                <input v-model="activeDay.notes[index]" class="ui-input" placeholder="市区停留 / 备注" />
                <button class="ui-button ui-button-danger px-2" type="button" aria-label="删除停留" @click="deleteNote(activeDay, index)">
                  <Trash2 class="ui-icon" aria-hidden="true" />
                </button>
              </div>
            </div>

            <button class="ui-button ui-button-danger w-fit" type="button" @click="deleteDay(activeDayIndex)">
              <span class="ui-icon-text">
                <Trash2 class="ui-icon" aria-hidden="true" />
                <span>删除当天</span>
              </span>
            </button>
          </div>

          <div v-else class="rounded-lg border border-dashed border-border bg-white p-4 text-sm font-semibold text-muted-foreground">
            暂无行程卡片
          </div>

          <div class="grid gap-2">
            <div class="flex items-center justify-between gap-2">
              <h3 class="ui-icon-text text-sm font-extrabold">
                <CircleDollarSign class="ui-icon text-primary" aria-hidden="true" />
                <span>费用文本</span>
              </h3>
              <span class="text-xs font-bold text-muted-foreground">{{ budgetText.trim() ? "已启用" : "未启用" }}</span>
            </div>
            <textarea
              v-model="budgetText"
              class="min-h-[116px] w-full resize-y rounded-lg border border-input bg-white px-3 py-2 text-sm leading-6 text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              placeholder="人数、电价、酒店、餐费、景区价格..."
            />
          </div>

          <div class="grid gap-2 rounded-lg border border-border bg-muted p-3">
            <div class="flex items-center justify-between gap-2">
              <span class="ui-icon-text text-sm font-extrabold">
                <CalendarDays class="ui-icon text-primary" aria-hidden="true" />
                <span>生成结果</span>
              </span>
              <span class="text-xs font-bold text-muted-foreground">{{ result?.out_dir || "trip-output/editor" }}</span>
            </div>
            <label class="flex w-fit cursor-pointer items-center gap-2 rounded-lg border border-border bg-white px-3 py-2 text-sm font-bold text-foreground">
              <input v-model="exportPdf" class="size-4 shrink-0 accent-[hsl(var(--primary))]" type="checkbox" />
              <span class="ui-icon-text">
                <FileDown class="ui-icon text-primary" aria-hidden="true" />
                <span>导出 PDF</span>
              </span>
            </label>
            <p v-if="error" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-bold text-destructive">{{ error }}</p>
            <div v-if="result" class="ui-action-group flex-wrap">
              <a v-if="result.output_url" class="ui-button ui-button-primary" :href="result.output_url" target="_blank" rel="noopener">
                <span class="ui-icon-text">
                  <Map class="ui-icon" aria-hidden="true" />
                  <span>打开网页</span>
                </span>
              </a>
              <a class="ui-button" :href="result.manifest_url" target="_blank" rel="noopener">
                <span class="ui-icon-text">
                  <FileJson class="ui-icon" aria-hidden="true" />
                  <span>manifest</span>
                </span>
              </a>
            </div>
            <div v-if="warnings.length" class="grid gap-2">
              <div v-for="warning in warnings" :key="warning" class="flex items-start gap-2 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs font-semibold text-orange-900">
                <AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <span class="min-w-0 break-words">{{ warning }}</span>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </main>
  </div>
</template>
