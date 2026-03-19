// Settings page - JiuwenClaw 配置
import { router } from '@kit.ArkUI'
import { mediaquery } from '@kit.ArkUI'
import { configService } from '../services/ConfigService'
import { ApiClient } from '../services/ApiClient'
import { ApiConfig, ApiMessage } from '../models/Types'

class McpServerEntry {
  name: string = ''
  url: string = ''
}

@Entry
@Component
struct SettingsPage {
  @State apiKey: string = ''
  @State baseUrl: string = 'https://api.deepseek.com/v1'
  @State model: string = 'deepseek-chat'
  @State maxTokens: number = 4096
  @State temperature: number = 0.7
  @State siliconFlowApiKey: string = ''
  @State mcpServerUrl: string = ''
  @State mcpServerName: string = ''
  @State statusMessage: string = ''
  @State isTesting: boolean = false
  @State isSaving: boolean = false
  @State isConnected: boolean = false
  private listener?: mediaquery.MediaQueryListener

  async aboutToAppear(): Promise<void> {
    this.apiKey = await configService.getApiKey()
    this.baseUrl = await configService.getBaseUrl()
    this.model = await configService.getModel()
    this.maxTokens = await configService.getMaxTokens()
    this.temperature = await configService.getTemperature()
    this.siliconFlowApiKey = await configService.getSiliconFlowApiKey()
    this.isConnected = this.apiKey.length > 0

    const mcpJson = await configService.getMcpServers()
    try {
      const servers = JSON.parse(mcpJson) as McpServerEntry[]
      if (servers.length > 0) {
        this.mcpServerName = servers[0].name
        this.mcpServerUrl = servers[0].url
      }
    } catch (e) {
      // ignore
    }
  }

  aboutToDisappear(): void {
    if (this.listener) {
      this.listener.off('change')
    }
  }

  async saveSettings(): Promise<void> {
    this.isSaving = true
    await configService.saveApiKey(this.apiKey)
    await configService.setBaseUrl(this.baseUrl)
    await configService.setModel(this.model)
    await configService.setMaxTokens(this.maxTokens)
    await configService.setTemperature(this.temperature)
    await configService.setSiliconFlowApiKey(this.siliconFlowApiKey)

    if (this.mcpServerUrl.length > 0) {
      const name = this.mcpServerName.length > 0 ? this.mcpServerName : 'MCP Server'
      const entry = new McpServerEntry()
      entry.name = name
      entry.url = this.mcpServerUrl
      const servers: McpServerEntry[] = [entry]
      await configService.setMcpServers(JSON.stringify(servers))
    } else {
      await configService.setMcpServers('[]')
    }

    this.statusMessage = '✅ 保存成功'
    this.isSaving = false
    this.isConnected = this.apiKey.length > 0
    setTimeout(() => {
      router.back({ url: 'pages/Index' })
    }, 600)
  }

  async testConnection(): Promise<void> {
    if (!this.apiKey) {
      this.statusMessage = '❌ 请输入 API Key'
      return
    }

    this.isTesting = true
    this.statusMessage = '测试中...'

    try {
      const config: ApiConfig = {
        apiKey: this.apiKey,
        baseUrl: this.baseUrl,
        model: this.model,
        maxTokens: 50,
        temperature: 0.7
      }

      const client = new ApiClient(config)
      const testMsg: ApiMessage = { role: 'user', content: '说"你好"' }
      const response = await client.sendMessage([testMsg])
      const reply = response.choices[0].message.content || '(空)'
      this.statusMessage = `✅ 成功: ${reply.substring(0, 20)}`
      this.isConnected = true
    } catch (e) {
      this.statusMessage = `❌ 失败: ${(e as Error).message}`
      this.isConnected = false
    }

    this.isTesting = false
  }

  build() {
    Column() {
      // 标题栏
      Row() {
        Text('←')
          .fontSize(20)
          .fontColor('#FFFFFF')
          .onClick(() => router.back({ url: 'pages/Index' }))

        Text('设置')
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor('#FFFFFF')
          .layoutWeight(1)
          .textAlign(TextAlign.Center)

        Row() {
          Circle()
            .width(8)
            .height(8)
            .fill(this.isConnected ? '#4ADE80' : '#F87171')
        }
      }
      .width('100%')
      .height(56)
      .padding({ left: 16, right: 16 })
      .linearGradient({ angle: 135, colors: [['#667EEA', 0], ['#764BA2', 1]] })

      // 内容区
      Scroll() {
        Column({ space: 12 }) {
          // API 配置卡片
          Column({ space: 12 }) {
            Row() {
              Text('🔌 API 配置')
                .fontSize(16)
                .fontWeight(FontWeight.Bold)
                .fontColor('#1F2937')
            }
            .width('100%')

            // API Key
            Column({ space: 6 }) {
              Text('API Key')
                .fontSize(13)
                .fontColor('#6B7280')
                .width('100%')
              TextInput({ text: this.apiKey, placeholder: 'sk-...' })
                .type(InputType.Password)
                .height(44)
                .width('100%')
                .backgroundColor('#F3F4F6')
                .borderRadius(10)
                .padding({ left: 12, right: 12 })
                .onChange((v: string) => this.apiKey = v)
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)

            // API 地址
            Column({ space: 6 }) {
              Text('API 地址')
                .fontSize(13)
                .fontColor('#6B7280')
                .width('100%')
              TextInput({ text: this.baseUrl, placeholder: 'https://api.deepseek.com/v1' })
                .height(44)
                .width('100%')
                .backgroundColor('#F3F4F6')
                .borderRadius(10)
                .padding({ left: 12, right: 12 })
                .onChange((v: string) => this.baseUrl = v)
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)

            // 模型
            Column({ space: 6 }) {
              Text('模型')
                .fontSize(13)
                .fontColor('#6B7280')
                .width('100%')
              TextInput({ text: this.model, placeholder: 'deepseek-chat' })
                .height(44)
                .width('100%')
                .backgroundColor('#F3F4F6')
                .borderRadius(10)
                .padding({ left: 12, right: 12 })
                .onChange((v: string) => this.model = v)
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)

            // Temperature
            Column({ space: 6 }) {
              Row() {
                Text('Temperature: ')
                  .fontSize(13)
                  .fontColor('#6B7280')
                Text(this.temperature.toFixed(1))
                  .fontSize(13)
                  .fontColor('#667EEA')
                  .fontWeight(FontWeight.Bold)
              }
              Slider({ value: this.temperature, min: 0, max: 2, step: 0.1 })
                .blockColor('#667EEA')
                .trackColor('#E5E7EB')
                .selectedColor('#667EEA')
                .width('100%')
                .onChange((v: number) => this.temperature = v)
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)

            // Max Tokens
            Column({ space: 6 }) {
              Row() {
                Text('Max Tokens: ')
                  .fontSize(13)
                  .fontColor('#6B7280')
                Text(this.maxTokens.toString())
                  .fontSize(13)
                  .fontColor('#667EEA')
                  .fontWeight(FontWeight.Bold)
              }
              Slider({ value: this.maxTokens, min: 1024, max: 32000, step: 1024 })
                .blockColor('#667EEA')
                .trackColor('#E5E7EB')
                .selectedColor('#667EEA')
                .width('100%')
                .onChange((v: number) => this.maxTokens = Math.floor(v))
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)

            // 按钮
            Row({ space: 10 }) {
              Button('测试连接')
                .height(42)
                .fontSize(14)
                .backgroundColor('#F3F4F6')
                .fontColor('#374151')
                .borderRadius(10)
                .layoutWeight(1)
                .enabled(!this.isTesting)
                .onClick(() => this.testConnection())

              Button('保存')
                .height(42)
                .fontSize(14)
                .backgroundColor('#667EEA')
                .fontColor('#FFFFFF')
                .borderRadius(10)
                .layoutWeight(1)
                .enabled(!this.isSaving)
                .onClick(() => this.saveSettings())
            }
            .width('100%')
          }
          .width('100%')
          .backgroundColor('#FFFFFF')
          .borderRadius(12)
          .padding(14)
          .alignItems(HorizontalAlign.Start)

          // RAG 配置
          Column({ space: 12 }) {
            Text('🧠 RAG 知识检索')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .fontColor('#1F2937')
              .width('100%')

            Column({ space: 6 }) {
              Text('SiliconFlow API Key')
                .fontSize(13)
                .fontColor('#6B7280')
                .width('100%')
              TextInput({ text: this.siliconFlowApiKey, placeholder: '可选，用于向量嵌入' })
                .type(InputType.Password)
                .height(44)
                .width('100%')
                .backgroundColor('#F3F4F6')
                .borderRadius(10)
                .padding({ left: 12, right: 12 })
                .onChange((v: string) => this.siliconFlowApiKey = v)
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)

            Text('留空则使用关键词检索')
              .fontSize(12)
              .fontColor('#9CA3AF')
              .width('100%')
          }
          .width('100%')
          .backgroundColor('#FFFFFF')
          .borderRadius(12)
          .padding(14)
          .alignItems(HorizontalAlign.Start)

          // MCP 配置
          Column({ space: 12 }) {
            Text('🌐 MCP 服务器')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .fontColor('#1F2937')
              .width('100%')

            Column({ space: 6 }) {
              Text('服务器名称')
                .fontSize(13)
                .fontColor('#6B7280')
                .width('100%')
              TextInput({ text: this.mcpServerName, placeholder: '如: 高德地图' })
                .height(44)
                .width('100%')
                .backgroundColor('#F3F4F6')
                .borderRadius(10)
                .padding({ left: 12, right: 12 })
                .onChange((v: string) => this.mcpServerName = v)
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)

            Column({ space: 6 }) {
              Text('服务器 URL')
                .fontSize(13)
                .fontColor('#6B7280')
                .width('100%')
              TextInput({ text: this.mcpServerUrl, placeholder: 'https://mcp.example.com/mcp' })
                .height(44)
                .width('100%')
                .backgroundColor('#F3F4F6')
                .borderRadius(10)
                .padding({ left: 12, right: 12 })
                .onChange((v: string) => this.mcpServerUrl = v)
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)

            Text('支持 Streamable HTTP MCP')
              .fontSize(12)
              .fontColor('#9CA3AF')
              .width('100%')
          }
          .width('100%')
          .backgroundColor('#FFFFFF')
          .borderRadius(12)
          .padding(14)
          .alignItems(HorizontalAlign.Start)

          // 状态消息
          if (this.statusMessage) {
            Text(this.statusMessage)
              .fontSize(13)
              .fontColor(this.statusMessage.startsWith('✅') ? '#10B981' : '#EF4444')
              .padding(12)
              .backgroundColor(this.statusMessage.startsWith('✅') ? '#ECFDF5' : '#FEF2F2')
              .borderRadius(10)
              .width('100%')
              .textAlign(TextAlign.Center)
          }

          // 底部
          Column({ space: 4 }) {
            Text('🐾 JiuwenClaw')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .fontColor('#667EEA')
            Text('懂你所想，自主演进')
              .fontSize(13)
              .fontColor('#6B7280')
          }
          .width('100%')
          .padding({ top: 16, bottom: 24 })
          .alignItems(HorizontalAlign.Center)
        }
        .width('100%')
        .padding(12)
      }
      .width('100%')
      .layoutWeight(1)
      .backgroundColor('#F9FAFB')
      .scrollBar(BarState.Off)
    }
    .width('100%')
    .height('100%')
  }
}
