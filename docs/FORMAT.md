# Lingfeng Lead Sheet 工程格式 v6

扩展名：`.lfs`（Lingfeng Lead Sheet）。格式标识：`org.lingfeng.leadsheet`。容器：ZIP。程序只读取固定成员，不向文件系统解压任意成员。

- `manifest.json`：`format`、`version: 6`、`document: project.json`、`sha256`。
- `project.json`：UTF-8 JSON，保存全部音乐与谱面状态。
- 文件与解压成员分别限制 32 MiB；不接受未知版本或不匹配的校验和。


## 音乐数据

时间为整数 tick，PPQ=960。所有音乐事件保存实际演奏顺序，不因谱面压缩而改变。

- `notes`：绝对起点、时值、MIDI 音高、力度、歌词、等音显示偏好、唯一 ID。
- `chords`：绝对起点、时值、根音、性质、指定低音、节奏型、gate、力度、八度、识别状态。`notes: null` 按节奏型生成；显式 `notes` 使用相对和弦起点 tick。显式音符也可匹配内置节奏；界面根据实际音符重新识别节奏型，允许不同配器与力度，不以存储方式判定“自定义”。识别结果不额外写入工程或改动音符。
- `contexts`：覆盖全曲的主音／调式区间。
- `measures`：拍号、段落名、手动换行；`marks` 保留旧版独立标记边界；批量设置应用于明确选中的小节；单小节还可独立向后应用调性或完整拍号。
- `volumes`：两轨 CC7 音量；`audio`：MIDI 设备与 GM program（0–127）。试听静音属于会话状态。
- `groups`：旧版命名时间分组的兼容字段，0.11 起不再提供编辑入口。

## 谱面数据

`notation` 保留 `style`、`per_line`、`circles`、`color`、`lyrics`、`row_gap`、`system_gap`，新增可选字段：

- `forced_rows`：`[[first_bar, end_bar_exclusive], …]`，从 0 开始的局部强制谱行，互不重叠。每行独立统一缩放、计算音域。
- `symbols`：`[{kind, start, end}, …]`，tick 选区中的谱面演奏提示。kind 为 `barline`、`double_bar`、`final_bar`、`segno`、`coda`、`fine`、`fade`、`rit`、`adlib`；`slur` 另保存旋律锚点 `note_ids`，详见 0.56.1 节。
- `compressions`：`[{kind, start, first_end, hidden_start, hidden_end, end}, …]`，索引为从 0 开始的小节边界，结束边界不含本身。kind 为 `repeat`、`dc`、`ds`、`dc_nr`、`ds_nr`、`coda`。

普通反复要求 `[start, first_end)` 与 `[hidden_start, hidden_end)` 相等且相邻。尾声为 A–B–A–C，第一 A 为 `[start, first_end)`，第二 A 为 `[hidden_start, hidden_end)`，C 到 `end`。仅合法匹配的第二 A 隐藏。音乐变化后失效的压缩保留记录但展开显示。

比较两轨实际事件、力度、等音偏好、拍号、段落名、调性与和弦标记；跨比较边界的持续音不可压缩。屏幕与 PDF 共用可见小节序列；MIDI 导出不读取这些排版字段。插入小节或改变拍号时，索引与符号 tick 随时间轴更新。

## 会话与本机偏好

0.57 新增本机布尔偏好 `rhythm_recognition`，缺省为 true。关闭后所有自动节奏型分析返回无识别结果，和弦轨不显示节奏型；根音／性质变换与区间编辑按实际 MIDI 处理，不借识别结果重建节奏。显式选择节奏型、重新生成和弦或应用和弦进行仍可按指定方案生成。开关不改写工程的 `pattern`、`custom_rhythm` 或 `recognition_disabled`，重新开启后按原有独立设置分析。节奏型合成与 MIDI 播放不依赖此识别偏好。

小节右键的“段落标识”继续写入 `measures[].section`；“跳转小节”按小节顺序列出现有标识与小节号，仅定位和浏览，不改工程。导航器用无文字边界线显示这些小节起点，原时间轴仍显示标识文字。

Since 0.57, the local boolean preference `rhythm_recognition` defaults to true. Turning it off bypasses every automatic rhythm analysis and hides pattern labels in chord lanes. Root/quality and region edits use performed MIDI rather than inferred patterns. Explicit pattern application, chord regeneration and progression generation remain available. The switch preserves project pattern and per-chord recognition flags; playback and synthesis do not depend on recognition. Bar context menus list marked sections in time order for navigation; navigators show their boundaries without text.

框选、剪贴板、停靠、滚动位置与静音属于会话状态。直接复制保留实际音高；其他变换使用调内级数，含调外源音时拒绝。粘贴结果仍存储普通 MIDI 音高。

本机 `preferences.json` 保存 `theme`、`language`、`colors`、`chord_order`（和弦性质代码偏好顺序）。`colors` 的 `light`／`dark` 下分别有 `background`／`note`，类别键为 `both`、`scale`、`chord`、`other`，值为颜色字符串。偏好不写入 MIDI/PDF。

0.9 的多个符号草稿及其 A/B 或 A/B/A′/C 区域选择仅为会话状态；应用时重新校验，成功后保存上述 compressions 或 symbols。右键渲染符号删除其所属记录，通过统一撤销栈还原，不修改音符事件。跟随播放游标开关和共享滚动位置也属于会话状态。比较时不比较歌词；绘制时将隐藏段落歌词按相对起点、音高及时长对应到可见音符，作为第二遍歌词。原始歌词保存在 notes 的兼容字段或 lyric_events 内，不合并、不改写源事件。

## 0.12 独立歌词（schema 5 可选字段）

`notation.lyric_events` 为时间事件数组，每项包含 `id`、`tick`、`text`、`verse`（0 起）、`voice`（0 起）、`pitch`（兼容元数据；无音高符号居中显示）。不要求对应 `Note.id`。导入 MIDI 或键盘录入前，把旧 `Note.lyric` 迁移到该数组并清空附着字段，保留时间和文字；输入 MIDI 中的歌词不覆盖它。

普通歌词在添加或修改时必须匹配旋律唯一 onset；进入制谱与导出 PDF 不再检查旧歌词匹配，不会以普通歌词缺音符自动生成 x。MIDI 导出依然输出独立歌词元事件。插入小节与改变拍号随音乐时间轴移动歌词；谱面反复压缩把隐藏段歌词映射到可见段并堆叠段次。


## 0.13 起点匹配与说唱（schema 5 可选字段）

`notation.lyric_sections` 保存编辑源段落：`id`、`start`（tick）、`verse`（0–31）、`text`。对应 `lyric_events` 增加 `section_id`、`kind`（note / skip / rap / rap_note）、`duration`、`skip`、`join_next`。段落确认先生成完整匹配计划，失败不改工程；同刻多声部只消费一个起点，普通字／音节和 `_` 均匹配旋律起点。`rap` 自带正时值，x 是渲染片段，不加入 Notes 或 MIDI note-on/off；非空歌词仍导出 MIDI lyric 元事件。

0.49 起中文逐字、英文按空格分割；`-` 与旧 `_` 均设 `skip`，不绘制文字或延音线。新歌词段保存 `syntax_version: 2`；缺省／1 的旧段落文本在编辑器中将英文连字符转为空格、`_` 转成 `-`，已存事件不重绑定。旧 `join_next` 字段保留以兼容旧英语音节显示。显式说唱 `/64.` = 90 ticks，`/64` = 60 ticks。未匹配的旧歌词允许保存和编辑 MIDI；只在添加／编辑歌词时校验，进入制谱及输出 PDF 不校验旧匹配。导入 MIDI 保留歌词事件，不自动重绑定。

插入小节会移动段落起点与事件，跨插入点的 rap 分成两段，后段 `text` 为空、`continuation=true`，不会重复输出歌词字。缩短拍号会裁切现有说唱节奏时要求先确认；其余时间变更随音乐轴移动。原始段落文本保留，重新确认会按当前起点重新匹配。

## 0.27 拍号与节奏型识别

和弦增加可选布尔字段 `bar_aligned`，缺省为 false 以兼容旧工程的相对起点节奏。经拍号修改或按小节生成的和弦设为 true，识别按实际小节相位及 `PATTERN_METERS` 的拍号支持范围进行，不再用与小节相位冲突的相对节奏补匹配。连续持续柱式仍允许跨同拍号小节不重新触发。`custom_rhythm` 的显式锁定优先于动态识别。

拍号变化先保留／裁切实际 MIDI，完成广播的全部拍号变更后，才按最终拍号边界拆分和弦并重新识别。加长小节在原末尾插入空白；缩短在末尾移除时间；等时长拍号变更不改旋律时间。schema 为 6，旧工程缺省字段由数据类补齐。

`notation.font_size` 为 0.0001–72（默认 15）的实际全局排版字号。排版计算的字号为建议，界面、打开及导出不将用户值压小；0.54 的传统全谱统一数字字号与立体强制合行差异见下文。通常为整数字号，极密内容也可保存四位小数。`notation.show_scale_lines` 默认 false，仅画 1／5 横线，true 显示其它调内横线。两项只影响谱面。


## 0.14 歌词小节范围

整小节确认的 `lyric_sections` 增加 `end`（排他 tick）。`start` 和 `end` 指定所选范围；编辑器以起始小节、数量显示。`&` 是待填模板，只用于预览，不进入已确认事件。`|` 保留在源文本中，用于把每段约束到单独小节；不使用分隔符时按整个范围依次匹配。允许仅填写范围内部分起点；未填 `&` 只用于预览，不保存事件。`|` 分段数量不超过所选小节数即可。同一段次不得重复匹配同一起点，文字及说唱时值不能越界。新增旋律起点不要求补齐歌词；已有文字失去音符起点时仍报告匹配错误。

旧工程不含 end 的段落仍按既有事件校验，打开时不自动改写歌词。重新确认时采用整小节范围。插入小节与拍号修改同步移动 start/end；实际歌词事件仍按原时间规则移动。

排版计算推荐字号，`0`、`x`、数字使用用户选定的同一基本字体与缩放；强制合行例外仍遵循整行缩放。`row_gap` 不被字体或多声部的隐藏最小值覆盖。谱面区域从顶部自动占满可用空间，无单独高度设置。调整音高间距可能改变推荐字号；推荐值不再覆盖用户输入。

## 0.21 小节节奏相位

工程版本仍为 v5。旧 `notes: null` 保留按和弦起点计算的演奏，打开工程不会重写 MIDI。新建、重新应用节奏型，以及已识别名称和节奏型的和弦移动／伸缩时，按每小节实际长度生成完整节奏，再裁取和弦区间，保存为相对起点的显式 `notes`。每小节重置节奏相位，包括持续柱式的小节起点；截断起点会重新触发仍在发声的音。`pattern` 保留识别提示，允许短片段与无音符的反拍片段维持已知名称和节奏。识别比较小节相位及旧相位，不改数据。

重新生成采用和弦默认配器、gate 与 velocity，逐音属性与 ID 重建；自定义节奏型平移或裁切时保留存续音符属性。根音半音移动与调内移动都将 `bass` 恢复为 null；右键替换低音是即时事件修改，不增加持久转位选项。

## 0.22 自定义节奏型锁定

和弦增加可选布尔字段 `custom_rhythm`，缺省为 false；仍使用 v5 容器。勾选时将生成式音符实体化，识别器始终返回自定义，移动只平移、伸缩只裁切。取消勾选不改音符。固定半音／八度移动设置该字段，应用内置节奏型清除它。复制和拆分继承；合并时任一来源锁定则保留锁定。试听方式与菜单选择状态不写入工程。

## 0.23 显示偏好与覆盖编辑

工程容器仍为 v5。和弦节奏表示和弦变化的频率，由各和弦区间起止体现；`pattern` 与 `custom_rhythm` 描述伴奏节奏型。不要将两者混为同一属性。

`preferences.json` 增加 `roll_coloring`：`melody` 和 `harmony` 各含布尔值 `scale`、`match`，默认均为 true。`match` 在旋律卷帘指和弦音匹配，在和弦卷帘指旋律音匹配。只影响卷帘绘制，不写入工程。独立窗口和主窗口的音量共同编辑工程 `volumes`，静音与绑定和弦轨显隐属于会话状态。

新建、拖动、拉伸及粘贴音符统一按同音高的时间交集覆盖：旧音符两侧保留，分裂出的右侧片段使用新 ID；不合并仅边界相接的音符。和弦卷帘按已有和弦边界分配音符，越过空区间时自动建立音符所需的和弦区间。此规则不改变其它音高的声部。

## 0.34：连续和弦 MIDI 与段落（schema 6）

当前保存格式为 `.lfs`（也接受 `.leadsheet`），ZIP manifest 的格式标识为 `org.lingfeng.leadsheet`，schema 为 6。读取同标识的 schema 5 或 6；schema 5 自动补缺省字段。其它旧容器及纯 JSON 不再作为工程文件读取。保存通过同目录临时文件原子替换，并校验 project.json 的 SHA-256。

`Note.event_id` 是可选字符串，默认空。和弦区间保留局部音符片段，其 `id` 唯一；同一连续 MIDI 事件的片段共享 `event_id`。播放、MIDI/MP3 导出与卷帘编辑从 `Project.harmony_notes()` 获取去重的绝对音符：仅将同事件、同音高、同力度且时间连续的片段连接。没有事件标识的相邻音符仍分别起音，禁止仅因同音高相接便合并。显式分割给后段分配新事件身份。

`Measure.section` 使用固定段落名（空字符串表示无新标识）。每次出现都开始一段，即使与前一段同名；末段结束于工程末尾。新项目与补齐空隙使用 `notes: []` 的和弦区间，显示 N.C.，无 MIDI 输出。和弦识别和区间布局不等同于完整和弦配器；缺省和弦音不会自动加入实际 MIDI。

用户偏好（工程目录、进行预设、升降号显示）保存在用户设置中，不属于工程内容。PDF 页码及 MIDI/MP3 导出范围也不修改工程。

0.35：预设段落标识统一为首字母大写，加载时按大小写不敏感匹配规范化旧标识；自定义旧段落文本保持原样，连续同名不合并。不改变 schema 或 MIDI。


## 0.39 和弦选项与性质兼容

schema 仍为 6。新增 `mM7`（0、3、7、11 半音），`add2`（0、2、4、7）替代 `add9`。读取旧 add9 时改名为 add2；显式音符原样保留，0.39 将旧生成型按原配器物化；0.40 起，旧生成型直接保留 notes=null，使用 add2 默认密集排列（显式 MIDI 仍原样保留）。进行配方中的 add9、菜单顺序中的 add9 均迁移为 add2；小大七的罗马数字为 iM7，也接受 ImM7。

本机偏好新增 `chord_edit_options`：root、quality、bass、pattern、gate（5–100 整数百分比）、velocity、octave、regenerate。不包含起点、时长、事件 ID 或实际音符；只在成功确认编辑后更新，取消或失败保留上次值。新对话框按当前和弦起点的拍号校验节奏型，不支持的生成型回退 block。此偏好不属于撤销历史或工程音乐数据。


## 0.40 密集 add2 与拍号相关的底五交替

schema 仍为 6。新增节奏型代码 alternating_quarters、alternating_eighths、alternating_offbeat，分子为偶数、分母为 2/4/8/16 时可用。低音单位为 PPQ*4/denominator，上方前两型使用 PPQ 与 PPQ/2，反拍在每个低音单位的后半拍起音并占半拍。每小节重新从根音开始，实际生成后保存为局部显式 MIDI。

add2 默认音程为 (0,2,4,7)，PyChord 注册级数为 (1,2,3,5)。旧 add9 的 notes=null 不再被物化成旧 1352 配器；用户已保存的显式 notes 不变。重新选择 add2 性质或应用节奏型时用默认配器生成。音符八度命令 octave_up/octave_down 以 ±12 半音编辑选区，默认 Ctrl+Up/Ctrl+Down；升级时已有快捷键占用优先，新命令可在设置中重新绑定。

## 0.40.1 统一快捷键设置

工程 schema 仍为 6。用户偏好 `keybindings` 统一保存文件、编辑、移动、工具、播放和选区命令；新增文件与剪贴板等命令，以及 `redo_alt`、`delete_alt`、`scale_up_alt`、`scale_down_alt` 备用键位和 `next_chord`。键位采用 Qt PortableText，空字符串表示禁用，缺失命令补默认值。载入时已有显式配置优先于新增默认配置，冲突的后续键位清空；旧默认工具与回放键迁移保持兼容。

编辑时输入冲突键位会列出被占用功能，确认后清空原绑定并转给当前功能；取消提示恢复原值，取消整个设置对话框不写入偏好。主菜单与右键菜单共享实际键位，备用键并列显示，禁用后不显示。Esc、Enter、Shift+Tab、Alt+F4 等固定控件／系统按键在设置中只读列出。文本编辑器仍使用自己的输入、剪贴板与撤销行为。


## 0.40.2 默认时值跟随与 7b5

工程 schema 仍为 6。新增质量代码 `7b5`，音程 (0,4,6,10)，书写级数 (1,3,5,7)，菜单名称“属七降五和弦”；PyChord 原生支持该代码。实际音符与已有其他质量保持兼容。

输入时值默认 -1（上一次时值）；记忆初始为空，查询时以起点的实际格点长度临时回退。记忆保存事件 ID 和最近有效长度，跟踪该事件后续修改；事件已删除时继续使用缓存的最近有效长度。创建、选择与编辑均更新记忆；失败或取消提交不替换成功编辑的记忆。每个卷帘分别保存会话状态，语言重建保留，新建／打开工程清空；不写入工程或用户偏好。


## 0.41 等宽制谱与内置播放

schema 保持 6。新建工程 melody.audio.program 默认 1，已有显式 program 不迁移；音源 device 新增 builtin，合法程序值为 0/1/4（原声／明亮／电钢琴）。离线合成读取同一程序值，其它 GM 编号明确回退为原声钢琴，Windows 实时录制仍使用系统默认 GM 输出。MIDI 导出保留程序编号，不嵌入音源。

每行所有可见小节等宽，时间映射严格线性，不按密度拉宽小节。符号按小节计算统一等比缩放，上限为用户 font_size；不改变实际音符时值、音高间距或分行数量。卷帘初始键高为 20。

## 0.42 采样音源迁移

schema 仍为 6。新建 audio.device 为 samples，melody.program=1、chords.program=0。samples 的合法程序值为 0,1,2,4,5,24,25,26,32,33,40,41,42,43,48。读取旧 builtin 自动迁移至 samples，保持原程序值；Windows 设备选项保留。工程不嵌入样本，发行包 sounds/ 提供资产，catalog.json 保存音色与许可信息。MIDI 仍输出 GM 程序编号，不嵌入专用音色。离线不再静默回退钢琴；未知编号提示改用 Windows 实时录制。


## 0.43 独立合成音源

schema 仍为 6。`audio.device` 支持稳定字符串 `synth:<pack-id>`；本轮为 `synth:stk-essentials` 和 `synth:stk-colors`。读取历史 `builtin` 或 `samples` 时迁移到基础包，保留 program，不依赖安装状态。Windows 选择保留。音源缺失不影响工程验证与保存；播放及离线导出时提示安装或重新扫描，不静默替换音色。

程序编号仍为 GM 0–127，实际可用集合由音源包清单定义。工程不包含音源二进制、采样或本机路径。新工程使用用户保存的两轨默认设置；无自定义默认且基础包存在时，旋律为基础包 program=1、和弦为 program=0；无基础包时初始为 Windows 默认音源。安装目录和扫描缓存独立于工程，详见 SOUNDBANKS.md。

## 0.44 主音与合并音源包

工程 schema 不变。进行库仍仅存 `name`、`sequence`，主音不持久化进配方；保存、应用、检索分别用本次所选主音换算。`synth:stk-acoustic` 为新的稳定音源 ID。预设清单增加可选 `cutoff_hz`，宿主要求相应 DLL 支持可选 `lf_tone` 接口；旧 ABI 1 包不含该字段时继续可用。`build-info.json` 记录本体/音源解压大小及合并包 ID。

## 0.44.1 显示与编辑记忆

工程 schema 不变。preferences.json 的 `chord_edit_options` 只读取/保存 `quality`、`pattern`、`gate`、`velocity`。旧 root、bass、octave、regenerate 字段在升级读取时丢弃。低音选择与根音相同仍存为 `bass: null`，避免冗余斜杠名称；用户选择其它音高时保存其音高类。界面的数字标号统一为调式音级，音高数据及进行库格式不变。

## 0.45 全局字号与两种空间映射

立体与紧凑简谱按密度分配小节宽度，每个小节内按实际时间等距排列，各拍长度相同；小节作为整体换行。全谱数字、休止符和说唱 x 共用字号，和弦、歌词及节奏符号随之等比缩放。首次进入制谱或切换谱式时自动设置推荐字号；手动修改后会保存，也可点击「推荐字号」重新计算。字号选项显示并限制在当前布局的不重叠上限，保持每行小节数；有效字号就是实际全局字号，音高间距保持设置值。布局改变会重新计算上限，旧工程超限字号会调整并保存为实际值。强制合行记录原每行小节数，按「原每行小节数 ÷ 合并后可见小节数」缩放，比例最大为 1；例如 4 小节合为 6 小节时使用全局字号的 2/3。传统简谱按音符、休止及延音横线等可见符号分配均匀位置，附点和升降号与音符一起保留空间。屏幕、点击定位、播放游标与 PDF 使用同一布局。

取代 0.41 的等宽小节和逐小节字号。`font_layout_version:45` 表示已自动设置或手动确认过本版字号，重新打开工程不覆盖。`forced_rows` 继续使用 `[start,end]`；可选 `forced_row_fonts` 为 `[start,end,original_per_line]` 列表，保存合并时的每行小节数基准；旧工程无此数据时使用当前 `per_line`。插入、删除小节会同步移动元数据，撤销、恢复自动分行及工程保存都保留正确关联。不修改旋律、和弦或 MIDI 时值。

## 0.46 拍间留白与查看状态

传统简谱的符号列仍等宽，每跨入新的拍组在列间增加 0.75 列留白，按 PPQ * 4 / denominator 分组。留白计入小节宽度与推荐字号；符号、延音与歌词中心不占用拍间留白。立体简谱的线性时间映射保持。

页面缩放、填满屏幕/整页模式及滚动位置是界面会话状态，不写入 .lfs，不修改 font_size 或 PDF 尺寸。制谱显示使用进入时的音乐快照；直接排版控制同步到该快照，音乐编辑等待下次切入。工程文件、MIDI 与音频始终使用最新音乐，制谱中的 PDF 使用当前显示快照。压缩段定位映射到可见源小节。

## 0.47 显示节奏与紧凑行

0.47 的传统简谱使用自然内容宽度，0.48 起改为两端对齐；缩短拍内符号间隔、谱行高度与小节线，保留歌词、八度点、减时线、复音与演奏记号的空间。强制合行仍保持原每行小节数对应的全局字号比例。

32 分音符对规则是纯派生布局，无新增工程字段。每个按分母划分的拍内，无 16 分音符（含附点/三连音写法）且恰有两个连续 32 分音符时，将相邻的附点八分音符片段由 720 tick 显示为 480 的占位，两个 120 tick 各按 240 占位，三条减时线保留；支持前置或后置附点片段、长音片段及附点休止。总拍宽与拍边界保持。长音只在布局 Fragment 中拆分并连线，display_duration 不进入 Note 或文件。空间映射仍以真实 tick 为索引，点击反算、播放游标、歌词、和弦和 PDF 共用映射。创作模式同时暂停隐藏谱面重绘和定位。

## 0.48 行边界和字号范围

传统简谱行范围为 `[MARGIN, PAPER_W-MARGIN]`，即 52–848；立体与紧凑谱仍在左侧预留 40 像素音高标记区。普通行、尾行、手动换行、压缩反复与强制合行使用相同边界。先按实际字号计算符号列和反复预留空间，剩余宽度按拍间隙数分给小节，再均匀加入小节内跨拍间隙；无间隙的小节留在末尾。小节总宽、符号列宽与时间映射共用这些结果，导出和点击位置一致。

布局暴露 `font_limit`，由横向空间和上下符号空间共同约束，在原有最大值 26 内向下取整；小于 1 时向下取四位小数。界面最大值与旁边的上限标签同步，超限旧值或布局变化后的值归一到上限，工程及谱面快照保存实际字号。普通谱行无额外隐式缩放，强制合行继续乘以已保存比例。保留 `font_layout_version:45`，避免版本升级覆盖已手动选择且仍合法的字号。没有改变音符或 MIDI 数据，也不自动改变每行小节数。


## 0.49 绑定现有音符的说唱

`/x{歌词}` 内的字符／词仍按唯一旋律 onset 匹配，事件保存 `kind: rap_note`、`duration: 0`（可省略），及与普通歌词相同的 tick、text、verse、section_id。括号必须成对，不支持嵌套或在组内附加显式时值。组内的 `-` 同样消耗起点、隐藏歌词，但该起点仍以 x 显示。

渲染时按事件 tick 找到对应旋律音符，将该起点的数字替换为无音高 x；同刻多声部合并显示，时长取对应音符最晚结束点。各谱式均使用与休止符 0 相同的中心位置。此投影不修改 notes、harmony、播放事件或 MIDI note-on/off；新歌词仍正常导出为 MIDI lyric 元事件。删除 rap_note 事件后恢复原数字。原 `rap` 类型自带正时值，用于兼容旧显式说唱，语义不变。

## 0.49.1 歌词范围回填

节奏点统一取 `notes` 中处于所选半开时间区间的唯一 `start`，不按音符结束时间过滤，不因跨小节延续而新增，也不纳入和弦轨。模板、节奏表、普通歌词与 `/x{}` 匹配共用此规则。

范围回填从实际 lyric events 重建各小节输入，空缺起点补 `&`，skip 输出 `-`，rap_note 输出 `/x{文字}`；显式 rap 保留可表达的时值与附点。仅查看范围不改工程。确认与删除按事件起点和 verse 限定，范围外事件及其 ID 保持；受影响的原歌词段保留剩余事件并更新其 start/end/text。新的整小节范围仍保存 `syntax_version: 2`，无新增文件格式字段。

回填后校验重新解析的文字是否保留原事件分配；旧版失去音符起点的歌词或无法无损表示的显式说唱仍显示在输入框，要求编辑后再确认，避免自动改绑。

## 0.49.2 混合文字与符号留白

中文逐字与英文逐词的边界可直接相邻。开引号／括号附在后续文字前，闭引号／标点附在前一文字后；拉丁字母之间的 `'` 或 `’` 属于英文缩写，不拆分。标点不把 `&` 变成已填歌词，也不为 `-` 产生可见文字。说唱组与范围回填共用解析规则，文件格式与事件绑定方式不变。

以 15 号音符的基准尺寸计，普通数字及减时线左右各预留 7，和弦音圈各 11；升降号左侧 18，附点右侧 15。符号横向总留白统一为 1.5。传统谱取对称包围盒，立体／紧凑谱保留原时间映射并按左右包围盒放置。0.53.1 起，字号推荐结合实际二维位置，允许用户主动超过建议；传统拍间距与逐拍宽度见更新日志。无新增工程字段。

## 0.49.3 歌词输入语法 3

新确认的 lyric_sections 使用 `syntax_version: 3`。`/-` 消耗一个旋律起点并保存 skip，普通 `-` 不再生成跳过起点。英文词内连字符保留；其它 Unicode 标点附在歌词上，不占起点。旧 syntax_version 1／2 的事件保持原位，编辑器从实际事件生成新格式，不按旧字符串重新匹配。

存在换行时，每行约束到对应小节，空行保留位置；末尾超出范围的空行可忽略，非空超出行报错。单行仍可连续匹配整个范围。旧 `|` 分隔文本仍兼容，`|` 后的排版换行只作为空白。连续 rap_note 回填为一个 `/x{...}`，可以跨行；每小节解析时保留 rap 状态。中间未填位置输出 `&`，每小节末尾未填位置省略。所有编辑仍按原有 tick／verse 范围覆盖，MIDI 音符不变。

## 0.49.4 歌词连音与行首续接

新歌词段使用 `syntax_version: 4`。`/s` 保存空文本的 skip 事件；`/-` 保存空文本的 skip 事件并附加 `melisma: true`。melisma 必须为布尔值，启用时 text 为空、skip 为真、duration 为 0。此字段只用于谱面，不写入或修改 MIDI 音符。旧事件无 melisma 时仍为跳过，旧源码不重新解释；编辑器根据已保存事件回填 `/s` 或 `/-`。

每个 melisma 从前一个唯一旋律 MIDI 起点连接到当前起点，多音同刻只算一个起点，同一对音符在多个段次中只绘制一次。`我/-/-` 绘制两段相邻连接。歌曲首个起点之前没有音符，`/-` 会报匹配错误；所选范围的首个起点可以连接范围外的前音。范围替换、删除、撤销和重做保留这一显示标志。

incoming 路径使用 y 单调向下的三次曲线，控制点都在端点高度范围内，垂直落差为基准 4 单位乘符号缩放；没有新的向上拱起。行首内缩跟随缩放，避免极小字号下反向。continuous 与 outgoing 保持原完整弧线。歌词连音与原时值延音分别记录为派生路径，不修改音符、命中区域和播放时间。

## 0.51 维护基线

本次仅整理源码与内部接口：工程 schema 6、manifest 标识、偏好 schema 1、歌词 syntax_version 4、音源 ABI 1 均保持原规则。工程仍只读取 `.lfs/.leadsheet` 的 manifest 5/6；不重新启用更早的 `.popscore`、纯 JSON 或 schema 2/3。重命名 Python 包不影响工程内的稳定 ID、音高、tick、歌词或音色字段。全部 13 个随附工程与 0.50.2 对比完整数据、播放事件和 MIDI 二进制保持一致。

## 0.53.1 逐拍列宽与建议字号

本节替代上述历史版本的传统拍间留白及强制字号上限。传统简谱的同一行共用符号格宽，各拍内容按自身可见符号数分配宽度；休止、延音横线计入，同刻多音共享列。所有拍之间，包括跨小节，使用同样的小间距；行末无额外拍组空白。强制合行时，间距与字号按既有 `forced_row_fonts` 的保存比例缩小。

`font_limit` 是基于实际二维符号位置的建议，不写入工程字号。`notation.font_size` 的合法范围扩大至 0.0001–72；打开、刷新、切换谱式和 PDF 导出保留手动值。显式「推荐字号」操作可采用推荐并撤销。`font_layout_version:45` 保留兼容；不新增工程字段，不改音乐与 MIDI。

## 0.53.2 传统连奏与跨拍记谱

本版不新增工程字段。传统简谱的切分、跨拍附点音在当地拍号的拍界拆分为记谱片段，以同一原音符 ID 的延音线连接；附点不跨出其拍界。拍内附点保持，拍首整拍长音保留延音横线。片段标记和声部分配仅为派生布局，不裁剪原始 notes，不改歌词事件、播放事件或 MIDI。

传统声部分配根据当前谱行可见片段计算占用。相邻、错开起音的短连奏尾部重叠可留在同一旋律行；真正同时起音和较长重叠仍分声部。立体／紧凑谱保留原有时值记谱规则。字号仍为用户选定值，建议上限及强制合行比例规则继续适用。

## 0.54 单声部入口与全谱数字单位

本地 0.54 当时的制谱入口仅接受严格单声部旋律（0.56.3 起仅传统简谱保留此限制），按原始 `notes` 的半开区间 `[start, end)` 检查。任意正时长重叠均报告，包括同刻起音、1 tick 或连奏短尾；相邻音符边界相接合法。检查不裁剪源音符、不按容差忽略重叠。`music.onsets` 的 `group_onsets`、`overlap_conflicts`、`is_monophonic` 保留完整 note_id/start/end/pitch 和同刻音组，供后续多声部扩展使用，不新增工程字段。

三种谱式均使用跨拍拆分和延音线，附点保持在当地拍界内，整拍长音保留延音横线。传统简谱每个可见片段或延音横线各占一个数字格，同刻源复音仅用于传统简谱的兼容渲染；0.56.3 起，复音不阻止进入立体／紧凑制谱，仅禁用传统简谱选项。数字格宽 `C` 由选定字号和实际数字字宽决定，在所有谱行相同。每行符号数为 `N`、拍数为 `B`，单位预算为 `N + 2B`；拍间 2 单位，小节线每侧和行边各 1 单位。最重谱行决定推荐字号并填满可用宽度，其它行维持 `C`，按 `G = (available - N*C)/(2B)` 分配线侧空白，拍间恒为 `2G`。手动超大字号保持自然格宽，间隙至少为 `C`，可能超出页面。推荐以数字为准，圈音、升降号等标记不额外撑宽格子。

传统强制合行也参与全谱预算，不再单独缩小该行的数字；旧 `forced_row_fonts` 元数据保留。立体／紧凑仍按“小节内最密拍起点数 × 实际拍数”分配小节宽度，小节内部各拍等宽，强制合行维持原比例。结构逻辑编辑页与对应命令暂时不开放，既有 `symbols`、`compressions` 和结构后端接口保留读取、保存及渲染兼容。

版本与交付分别记录：默认构建仅更新本地独立程序目录，不生成或更新 ZIP/SHA-256 文件；只有明确指定 `-Archive` / `--archive` 才创建新发行归档。`CHANGELOG_LOCAL.md` 记录本地工作，`CHANGELOG.md` 只记录已有发行归档节点。工程 schema 6、偏好 schema 1、音源 ABI 1 及音乐数据不变。

## 0.54.1 圈音单位、整数推荐与减时线

传统简谱的数字单位改为圈音外框的水平宽度：基准椭圆宽 20，加描边 0.95，共 20.95；与实际数字字宽的比值统一作用于每个字符和间隔单位。所有数字、休止、说唱 x、延音横线均共用该格宽，关闭圈音也不改变布局。`N + 2B`、最密行及其它行的 `G/2G` 分配不变。推荐字号取原始适配上限的整数下界，最低为 1；极密谱面在最小正整数字号下仍可能超宽。手动小数值仍合法，不由推荐自动覆盖。

每个传统谱行记录实际显示的最大下八度点数。第一条减时线沿用该行最低音符所需的下移量，其余音符和休止采用相同高度；后续减时线按原 4 单位等距平行排列。兼容渲染中的不同声部在各自基线上采用相同偏移。字形包围盒、声部间隔、歌词、行高和分页共用该下边界。立体／紧凑谱的字号和节奏高度规则不变，无新增持久化字段。

## 0.54.2 固定纸面适配与三连音组

A4 纸面尺寸不变。排版保留原始字符格、手动字号、每行小节数及强制合行信息，在绘制前为超宽或超高的谱行应用统一的等比例纸面变换，并按适配后的行高分页；圆圈不被横向压扁。容得下的行保持原比例。字体设置与推荐字号仍分开保存，纸面适配不回写 `font_size`。屏幕、PDF、选择、音符点击、播放线与定位使用相同的纸面坐标；派生变换不增加工程字段。

三连音先按原始起点和时值识别连续组，再收集属于该组的可见显示片段。跨拍或跨小节拆分不增加组三连音数量，也不把普通音符的三连音长度碎片认作新的三连音。每个可见谱行段在整组上方画一个水平括号与数字 3，避开数字、八度点和延音弧线；跨行或跨页保留对应组的分段括号。源音符、时值、歌词关联和 MIDI 不改变。

## 0.54.3 推荐字号与强制行绑定（取代 0.54.2 整行缩放）

不再应用整行纸面比例变换，`layout_scale` 恒为 1。传统简谱完整预算为 `U = N + 2B`：每个显示片段、休止、说唱 x 或延音横线各占一个字符单位，拍间及小节线两侧仍按 2:1 分配。取当前非强制行的最大 U 为参考；推荐字号为 `floor(15 * 可用宽度 / (20.95 * U参考))`，最低 1、最高 72。

每个强制行由当前可见的片段和横线重新计数，字号比例 `r = min(1, U参考 / U强制)`，实际字符字号为全局字号乘 r，字符格 C 同比例变化，再以剩余空间分配 G/2G。强制行不压低普通行的全局建议。若所有行都被强制，按当前 `per_line`、显式换行和可见小节建立忽略合行的参考分组；`forced_row_fonts` 的历史小节数信息继续可读，但不作为传统谱的字体比例。

修改行容量、传统谱式、换行、合行或恢复行时，把字号推荐与排版变更保存为同一个撤销步骤；制谱重新接收预算变化的音乐时重算推荐，首次进入会减小超出建议的初始传统字号。普通刷新、保存和显式手动字号不暗中缩放整行，手动超出建议仍按所选自然字号绘制。推荐仅按上述符号预算，不用任意长度的注释撑缩整张谱行。没有新增持久化字段，源音乐和 MIDI 不变。

## 0.55 和弦力度选项 / Chord velocity options

工程仍为 schema 6，偏好 schema 1，音源 ABI 1。右键力度修改现有 `Chord.velocity` 及非空实际音符的 `Note.velocity`，不增加工程字段；生成型和弦继续按既有力度参数产生音符，静音空区间保持为空。一次批量修改为一个撤销步骤。偏好新增 `chord_velocity_options` 整数数组，保存 1–127 的去重升序值；缺失或无有效值时使用 `[32,48,64,80,96,112,127]`，损坏类型不传入菜单。

Project schema 6, preference schema 1 and sound ABI 1 remain unchanged. Batch edits update existing chord/note velocities in one undo step. The additive `chord_velocity_options` preference stores unique, sorted MIDI values from 1–127; missing or invalid lists use the common defaults. Detection results enter this list only after explicit confirmation and never rewrite project sound selections.

## 0.56 识别开关、显示标记及创建偏好 / Recognition and creation preferences

工程保持 schema 6。`Chord.recognition_disabled` 与 `Chord.marked` 是默认 `false` 的增量布尔字段。禁用和弦识别先实体化原音符，再跳过和弦与节奏型识别；`custom_rhythm` 仍独立保存，单独启用不影响和弦识别。手工标记使用现有 `root`、`quality`、`bass`，并设置两个新字段及 `recognized=true`，影响名称与罗马符号；0.56.3 起也为旋律卷帘的和弦匹配染色与弦内音高亮提供音级，不生成或替换 MIDI 音符。恢复识别先移除标记，再从实际 MIDI 重新推断；原独立节奏型禁用偏好仍有效。标记支持撤销、复制、分割与保存。MIDI 导出的演奏事件不变，和弦文字元事件可反映新标识。

偏好新增 `default_velocities: {melody:92, harmony:72}`，仅接受 1–127 整数。旋律卷帘新建音符读取 melody；0.56.2 起，和弦卷帘按新音符起点所在和弦块读取 `Chord.velocity`，没有和弦块时回退 harmony。编辑和弦每次读取 harmony 默认值，忽略旧 `chord_edit_options.velocity`。保留音符的编辑不重写实际音符力度。`quick_chord_qualities` 保存勾选的性质代码及顺序，允许空数组；旧 `chord_order` 迁移为原常用性质的顺序。完整性质与数字关系始终可在设置预览，与快捷列表选择无关。

Project schema 6 and preferences schema 1 remain compatible through additive fields. A manual mark materializes existing notes before changing symbol fields; performed note events retain their IDs, pitches, timing and velocities. Disabling chord recognition also blocks pattern recognition, while `custom_rhythm` independently blocks only patterns. Resuming recognition removes the manual mark and derives a fresh symbol from actual MIDI. Default velocities and selected, ordered quick qualities are user preferences; the complete quality reference remains available in Settings.

PyChord 1.4.2 的 104 个原生性质／同义名称，加上保留的紧密 `add2`，共 105 项。`add9` 新建时使用 1 3 5 9 并正常往返；旧工程的和弦条目同时缺少两个新识别字段时，仍按旧版含义迁移 `add9` 为 `add2`，实际音符保持。省五性质的底五交替在缺少五音时重复原低音，不增加和弦外的自然五音；同时存在 b9、#9 的性质保留两个声部。

## 0.56.1 低音力度、显示范围及谱面标识 / Bass dynamics and score annotations

工程 schema 仍为 6，偏好 schema 仍为 1。0.56.1 曾引入可选的 `Chord.bass_velocity`（`null` 或 1–127 整数），为生成型和弦的低音声部设置单独力度；底五交替的低音根音与五音共用此值。该独立参数与操作已于 0.56.2 取消，旧字段读取迁移规则见下节。显式 `notes` 始终是实际演奏数据。低音仍属于和弦轨内的 MIDI 声部，没有增加轨道。

0.56.1 曾在 `default_velocities` 中增加 `bass:72`，0.56.2 起忽略此旧偏好，仅保留 melody／harmony。和弦编辑每次从 harmony 默认值初始化统一力度；保留实际音符时不回写默认值。两个卷帘的音符菜单、逐音力度轴与和弦整体力度轴的数值输入仍使用相应已保存全局默认值，独立于当前事件及前次输入。跨和弦区间合并相邻／重叠的同音高音符使用现有连续事件与 `event_id` 投影机制，保留区间边界；跨界播放和 MIDI 导出不重触发。

自定义卷帘范围保存为会话内的闭区间 MIDI 音高二元组，限制 `21 <= low <= high <= 108`。全键、已用与手动范围是显示模式，不进入 `.lfs` 或用户偏好，不删除范围外音符或改动 MIDI。停靠卷帘共享范围；浮窗独立，时间轴同步不覆盖其音高范围。切换语言保存并恢复该视图状态。

`notation.symbols` 增加 `kind: slur`，条目为 `{kind, start, end, note_ids}`。`note_ids` 保存至少两个唯一的旋律音符 ID；创建时要求首末音符的起点不同，按演奏时间排序。`start/end` 是创建时首音起点及末音结束点；渲染以仍存在的 ID 查找当前音符，缺失足够锚点时不绘制。整组从首音至末音为一条乐句弧，跨行、跨页派生为连续片段，支持中间整行的贯穿段。它与歌词 `melisma` 逐对连音及源音符延音线相互独立，只影响谱面和 PDF，不合并或改写 MIDI。增删支持工程保存与同一撤销历史。

制谱的旋律、和弦、歌词和标识四个面板初始均隐藏，各自显隐、停靠、浮动属于会话状态；视图菜单分别打开，语言和工作区切换保留。标识面板复用既有 barline、double_bar、final_bar、segno、coda、fine、fade、rit、adlib 与新 slur 项；反复压缩和跳转编辑仍不开放。

Version 0.56.1 introduced an optional bass-velocity field and bass default, retired by 0.56.2 through the migration described below. Project and preference schemas remain compatible. Custom key ranges, panel visibility and menu grouping are view state. Phrase slurs persist as note-ID-anchored score symbols; MIDI event pitches, timing and playback order are unaffected by display settings or annotations.

## 0.56.2 统一力度、设置模块与菜单布局 / Common velocity, settings modules and context menus

工程 schema 仍为 6。新和弦只使用 `Chord.velocity`，生成与重新生成对全部声部应用同一力度；不再提供独立低音力度 API 或 UI。`Project.from_dict` 读取旧 `bass_velocity` 时，已有显式 `notes` 原样保留；旧生成型和弦先按原低音规则物化为显式音符，再移除旧字段，因此加载与另存不会改变原 MIDI 演奏。后续明确重新生成时才统一采用 `Chord.velocity`。`to_dict` 不再输出 `bass_velocity`。逐音编辑仍可保存不同的 `Note.velocity`。

偏好 `default_velocities` 只保存 `melody` 与 `harmony`，旧 `bass` 值忽略。旋律卷帘新建音符使用 melody；和弦卷帘的绘制、双击等创建入口按音符起点选择所在和弦块的 `velocity`，包含空白和弦块；没有所在和弦块时使用 harmony。每个块使用半开区间 `[start, end)`，边界处采用后一块。和弦编辑对话框继续每次使用全局 harmony 默认值，取消重新生成保留实际音符。

设置按音源与输入、音符与力度、和弦、卷帘显示、界面与操作组织。音符与力度在同一对话框组合两个默认力度、`chord_velocity_options` 列表及按按钮检测当前和弦音源；确认后一起保存，取消不修改。快速性质与完整目录由和弦性质窗口独立管理。模块布局不改写工程音乐，手动音源检测仍不在启动或打开设置时触发。

Project schema 6 remains compatible. Loading a legacy generated chord with `bass_velocity` first materializes the original performance as explicit notes; existing explicit notes retain their saved velocities. New serialization omits the retired field, and later regeneration applies one common chord velocity. The only saved creation defaults are melody and harmony. Chord-roll creation uses the region at the note onset, falling back to the harmony default outside regions; the chord editor still starts from the global harmony default. Modular settings combine defaults and velocity presets in one transaction and keep sound inspection opt-in.

偏好 schema 仍为 1。`context_menu_layout` 分别保存 `chord` 与 `note` 的功能块数组，每项为 `{id, grouped}`；数组顺序决定菜单顺序，稳定的 `id` 与中英文显示名分离。`grouped` 只对允许分组的功能块生效，复制、粘贴、分割与合并等固定直显功能不会因偏好而隐藏。未知、重复或无效条目忽略，缺失的现有功能块按默认顺序补齐；菜单设置取消不改偏好，确认后保存。

三种伴奏节奏型的中文名称统一为“底五交替”，原有 `alternating_quarters`、`alternating_eighths`、`alternating_offbeat` 代码与演奏规则保持。对话框统一使用“编辑音符”“编辑和弦”“和弦标记”，罗马数字预览与以根音为 1 的数字关系分别标注；力度使用 MIDI 1–127，音高范围选项明确显示 MIDI 编号。以上显示名称与菜单布局均不改变工程 schema、音符或 MIDI。

Preference schema 1 stores ordered chord and note block IDs with optional submenu grouping in `context_menu_layout`. Localized titles are independent of those IDs. Fixed direct commands remain visible, malformed entries are ignored, and missing blocks are restored. The alternating-bass display rename retains its three existing pattern codes and performance rules; text and menu preferences do not change project data or MIDI.

## 0.56.3 多声部制谱与手动标记高亮 / Polyphonic scores and manual-mark highlighting

工程 schema 6、偏好 schema 1 不变。旋律多声部允许进入立体（`spatial`）与紧凑（`compact`）制谱；只有传统（`traditional`）要求严格单声部。检测继续使用原始 `notes` 半开区间 `[start, end)`，任何正时长重叠（包括同刻起音、1 tick 与连奏短尾）均使传统选项不可用；边界恰好相接合法。读取 `traditional` 加复音的工程、恢复制谱布局或编辑／历史操作产生不兼容时，自动回退 `spatial`，保留制谱工作区与全部音乐。修复为单声部后传统恢复可选，不会裁剪或删除音符。

制谱仍使用进入时同步的音乐快照，普通音乐编辑按既有规则在重新进入制谱时同步。例外是最新音乐已修复为单声部而旧快照仍复音：切换传统时先同步修复后的音乐，再生成传统谱面。立体／紧凑 PDF 可包含多声部；传统加复音在导出界面禁用，直接 PDF API 抛出错误，并在创建／覆盖目标文件之前拒绝，不修改原文件。

`Chord.marked=true` 的旋律卷帘和弦匹配染色及弦内音高亮，由标记的 `root`、`quality`、`bass` 推导音高类，包含指定低音与没有实际音符的标记区间，跨八度应用。普通未标记和弦仍按所在区间实际演奏音高类显示；解除手动标记后恢复该规则。标记修改、撤销／重做、保存重开与停靠／悬浮旋律卷帘采用相同依据。此显示投影不改 `Note`、事件 ID、音高、起止或力度；0.56.3 时谱面圈音仍依据实际和弦 MIDI，0.56.4 起扩展为手动标记优先规则（见下节）；和弦卷帘的旋律匹配继续依据实际旋律音符。

Project schema 6 and preference schema 1 remain unchanged. Spatial and Compact scores allow polyphonic melodies; only Traditional requires strict monophony. Any positive-duration overlap disables Traditional, while exactly adjacent boundaries are legal. Loading, restoring, editing or history operations that make Traditional incompatible fall back to Spatial without leaving Score or changing notes. Traditional becomes available again once the live melody is monophonic. If the displayed snapshot still has polyphony but the live melody has been corrected, choosing Traditional first synchronizes the corrected music; ordinary snapshot updates retain their existing re-entry behavior. Spatial/Compact PDFs allow polyphony. Traditional PDF export with overlaps is disabled in the UI and rejected by the direct API before changing any destination file.

Manual chord marks derive melody-roll chord-match coloring and chord-tone row highlights from their root, quality and explicit bass, including empty marked regions and other octaves. Unmarked chords continue to use actual performed pitch classes. This display projection preserves all MIDI events and note properties. Score circles retained the actual-MIDI rule in 0.56.3; version 0.56.4 extends them to manual marks as described below. Melody matching within the chord piano roll continues to use actual MIDI.

## 0.56.4 拍中点优先分解与标记圈音 / Offbeat-first decomposition and marked chord circles

工程 schema 6、偏好 schema 1 不变。三种谱式的有音高旋律音符先保留原有整拍延音横线特例，再按当地拍号的拍界强制拆分并连接同一源音符。对拍内片段，能由单个普通、单附点或三连音音值表示时保持单个符号，沿用 ±2 tick 的既有容差，不因跨过拍中点而额外拆分。

仅当拍内有音高片段确实需要多个符值、且跨过当前拍中点（offbeat）时，优先在该中点拆分并加延音线，再对左右两侧沿用原符值分解；未跨中点保持原贪心回退。中点按本小节起点与当地拍号分母确定的拍长计算，并非固定 480 tick。以 PPQ=960、4/4、起点 3000、时长 840 为例，原先的 720+120 分解改为 360+480，在 tick 3360 的拍中点连线，片段总时长仍为 840。该例使用实际时间值，不从图形宽度推断 tick。新增中点优先规则不应用于休止符；独立的 32 分音符对显示借位、原三连音组与跨拍连线继续保持。源音符 ID、音高、起止、力度、播放及导出 MIDI 不变，显示片段不写入工程。

谱面弦内音圈统一读取 `Chord.highlight_pcs`，与旋律卷帘匹配显示共用依据。手动标记（`marked=true`）使用 `root`、`quality`、`bass` 推导音高类，包含指定低音、其它八度及没有实际音符的标记区间；未标记和弦仍读取实际 `render_notes` 的音高类。显示的旋律音符符合该音级且启用圈音时才绘制圆圈；标记不会生成演奏音符。屏幕、PDF 与圈音墨迹／字号计算使用同一判定；谱面仍使用当前音乐快照。悬停中的实际和弦音符详情、和弦卷帘的旋律匹配及 MIDI 继续依据真实演奏。

Project schema 6 and preference schema 1 remain unchanged. Pitched notes retain the existing whole-beat extension-dash exception and mandatory splits and ties at local beat boundaries. An in-beat fragment that fits one plain, single-dotted or triplet value remains one symbol, including the existing ±2-tick tolerance. Only a fragment requiring decomposition that crosses the beat midpoint splits and ties there first; each side then uses the prior value decomposition. Without a midpoint crossing, the greedy fallback remains. Midpoints follow the local meter and bar origin, not a fixed 480-tick grid. At PPQ=960 in 4/4, onset 3000 and duration 840 changes from 720+120 to 360+480, tied at tick 3360, preserving the exact duration. Rests do not use the new midpoint-first rule. Source notes and MIDI are unchanged; the existing isolated-32nd spacing and source-triplet rules remain.

Score chord-tone circles now share `Chord.highlight_pcs` with melody-roll matching. Manual marks derive pitch classes from root, quality and explicit bass, including empty marked regions and other octaves; unmarked chords use actual performed pitches. The circle toggle, screen/PDF rendering and circle-ink font calculations share this rule within the current score snapshot. Performed-note hover details, chord-roll melody matching and MIDI retain actual performance data.

## 0.56.5 持续低音与复制事件 / Sustained bass and copied events

新增节奏代码 `sustained_bass_beats`（持续低音 + 每拍和弦）：按当地小节生成整小节低音，上方和弦声部按拍号分母逐拍触发并持续整拍；忽略 gate，裁切到和弦区间，跨小节重新触发。沿用 schema 6、显式 notes 与既有 pattern 提示，不更改旧工程的音符。

和弦粘贴保留实际音高、配器、相对起止和逐音力度，不按识别到的节奏型重建默认配器。为每次副本分配独立音符 ID 和共享事件 ID；同一副本内跨区间的持续音仍共享新 event_id，与源音符和其它副本互不连接。右键和弦的覆盖粘贴从被点击和弦的起点开始，定位线粘贴保留。方向键及 Alt 调内／Ctrl 八度组合固定，旧快捷键设置自动迁移；镜头移动绑定暂时留空。

The `sustained_bass_beats` pattern holds the bass for each local bar and the upper voices for every denominator beat, ignoring gate and cropping to chord regions. Pastes retain performed pitches, voicing, timing and per-note velocities without template regeneration. Each paste receives independent note and shared-event identities, preserving internal cross-region sustains without joining the source or other copies. Chord context pastes overwrite from the clicked chord start; position-marker paste remains available. Movement arrows and scale/octave modifier combinations are fixed; older preferences migrate and camera bindings remain blank. Schema 6 is unchanged.

## 0.56.6 粘贴裁切与自动连音 / Cropped pastes and automatic lyric slurs

非空和弦剪贴板允许在任意目标拍号粘贴；来源 `meters` 仅保留会话兼容，不再限制目标。整批粘贴裁切到目标起点所在连续拍号区间的末尾与工程末尾中的较早者，当前块的显式音符截短，超出片段和后续块舍弃。曲尾起点安全不操作；不自动增加小节。范围剪贴板仍保留相对起点／间隙，旋律只按工程末尾裁切。副本事件 ID 独立映射及内部延音共享规则沿用 0.56.5。

歌词连音直接由 `melisma: true` 事件及当前谱面音乐派生，与手动标识分开管理，不写入 `notation.symbols`。歌词连音优先：冲突的手动连音弧不可新建，已有冲突项只在显示中静默隐藏，不删除工程数据；移除冲突歌词后恢复。修改或删除歌词、撤销／重做后自动更新。旧跳过事件及其它类型标识保持；自动弧跨行／跨页包含中间续接段。撤销保存的视图锚点属于会话状态，以音乐时间及音高行恢复，不写入工程。

Chord pastes no longer enforce source meter metadata. The batch stops at the destination’s continuous meter-region or project boundary, cropping performed note durations without regeneration or added bars. Range clips retain relative starts; melody content crops only at the project end. Automatic lyric slurs derive from melisma events and remain separate from persisted manual symbols. Lyric slurs take priority: new conflicting manual arcs are blocked, while existing conflicts are hidden without deleting their data and return when the conflict is removed. Automatic arcs continue across intervening rows and pages. Undo view anchors are session state only. Schema 6 is unchanged.
