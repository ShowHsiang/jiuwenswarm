// JiuwenClaw - Main Chat Page
import { router } from '@kit.ArkUI'
import { agentCore } from '../services/AgentCore'
import { dbService } from '../services/DatabaseService'
import { configService } from '../services/ConfigService'
import { AgentEvent, ToolCallRecord } from '../models/Types'
import { generateId } from '../utils/TextFormatter'

interface MsgItem {
  id: string
  content: string
  isUser: boolean
  isThinking: boolean
}

@Entry
@Component
struct Index {
  @State msgList: MsgItem[] = []
  @State inputVal: string = ''
  @State loading: boolean = false
  @State hasKey: boolean = false
  @State toolInfo: string = ''
  @State showActions: boolean = false
  private chatId: string = 'default'
  private scroller: Scroller = new Scroller()

  aboutToAppear(): void {
    this.initData()
  }

  onPageShow(): void {
    this.initData()
  }

  async initData(): Promise<void> {
    this.hasKey = await configService.hasApiKey()
    if (this.hasKey) {
      const msgs = await dbService.getMessages(this.chatId, 50)
      this.msgList = []
      for (const m of msgs) {
        this.msgList.push({
          id: m.id,
          content: m.content,
          isUser: m.isFromMe,
          isThinking: false
        })
      }
    }
  }

  async sendMsg(): Promise<void> {
    const text = this.inputVal.trim()
    if (text.length === 0 || this.loading) {
      return
    }

    this.inputVal = ''
    this.loading = true

    // 用户消息
    const userMsg: MsgItem = {
      id: generateId(),
      content: text,
      isUser: true,
      isThinking: false
    }
    this.msgList.push(userMsg)

    // 思考中
    const thinkId: string = generateId()
    const thinkMsg: MsgItem = {
      id: thinkId,
      content: '思考中...',
      isUser: false,
      isThinking: true
    }
    this.msgList.push(thinkMsg)

    setTimeout((): void => {
      this.scroller.scrollToIndex(this.msgList.length - 1)
    }, 100)

    // 调用 Agent
    agentCore.runAgent(text, this.chatId, (event: AgentEvent): void => {
      if (event.type === 'tool_use') {
        this.toolInfo = '🔧 ' + (event.name || '')
      } else if (event.type === 'text') {
        const idx = this.msgList.findIndex((m: MsgItem): boolean => m.id === thinkId)
        if (idx >= 0) {
          const replyMsg: MsgItem = {
            id: generateId(),
            content: event.content || '',
            isUser: false,
            isThinking: false
          }
          this.msgList[idx] = replyMsg
        }
      } else if (event.type === 'error') {
        const idx = this.msgList.findIndex((m: MsgItem): boolean => m.id === thinkId)
        if (idx >= 0) {
          const errMsg: MsgItem = {
            id: generateId(),
            content: '错误: ' + (event.error || '未知'),
            isUser: false,
            isThinking: false
          }
          this.msgList[idx] = errMsg
        }
      } else if (event.type === 'done') {
        this.loading = false
        this.toolInfo = ''
      }
    }).then((): void => {
      this.loading = false
    })
  }

  async doAction(action: string): Promise<void> {
    this.showActions = false
    if (action === 'clear') {
      await dbService.clearChat(this.chatId)
      this.msgList = []
      return
    }
    
    let prompt: string = ''
    if (action === 'memory') {
      prompt = '/memory'
    } else if (action === 'tasks') {
      prompt = '/tasks'
    } else if (action === 'evolution') {
      prompt = '/evolution'
    } else if (action === 'context') {
      prompt = '/context'
    } else if (action === 'files') {
      prompt = '列出文件目录'
    } else if (action === 'search') {
      prompt = '搜索今天的热门新闻'
    } else if (action === 'note') {
      prompt = '帮我创建一个笔记文件'
    }
    
    if (prompt.length > 0) {
      this.inputVal = prompt
      await this.sendMsg()
    }
  }

  build() {
    Column() {
      // 标题栏
      Row() {
        Text('JiuwenClaw')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .fontColor('#FFFFFF')
        
        Blank()
        
        Button('⚙️')
          .fontSize(16)
          .width(36)
          .height(36)
          .backgroundColor('#FFFFFF20')
          .borderRadius(18)
          .onClick((): void => {
            router.pushUrl({ url: 'pages/SettingsPage' })
          })
      }
      .width('100%')
      .height(56)
      .padding({ left: 16, right: 12 })
      .linearGradient({ angle: 135, colors: [['#667EEA', 0], ['#764BA2', 1]] })

      if (!this.hasKey) {
        // 欢迎页
        Column() {
          Text('🐾')
            .fontSize(64)
            .margin({ bottom: 20 })
          
          Text('欢迎使用 JiuwenClaw')
            .fontSize(24)
            .fontWeight(FontWeight.Bold)
            .fontColor('#1F2937')
            .margin({ bottom: 8 })
          
          Text('懂你所想，自主演进')
            .fontSize(16)
            .fontColor('#6B7280')
            .margin({ bottom: 32 })
          
          Button('前往设置')
            .width(180)
            .height(44)
            .fontSize(16)
            .backgroundColor('#667EEA')
            .fontColor('#FFFFFF')
            .borderRadius(22)
            .onClick((): void => {
              router.pushUrl({ url: 'pages/SettingsPage' })
            })
        }
        .width('100%')
        .layoutWeight(1)
        .justifyContent(FlexAlign.Center)
        .backgroundColor('#F9FAFB')
      } else {
        // 消息列表
        List({ scroller: this.scroller }) {
          ForEach(this.msgList, (msg: MsgItem) => {
            ListItem() {
              Row() {
                if (msg.isUser) {
                  Blank()
                }
                
                if (msg.isThinking) {
                  Row() {
                    LoadingProgress().width(18).height(18).color('#667EEA')
                    Text(' 思考中...').fontSize(14).fontColor('#6B7280')
                  }
                  .padding(12)
                  .backgroundColor('#F3F4F6')
                  .borderRadius(16)
                } else {
                  Text(msg.content)
                    .fontSize(15)
                    .fontColor(msg.isUser ? '#FFFFFF' : '#374151')
                    .padding(12)
                    .backgroundColor(msg.isUser ? '#667EEA' : '#FFFFFF')
                    .borderRadius(16)
                    .constraintSize({ maxWidth: '80%' })
                    .shadow(msg.isUser ? undefined : { radius: 4, color: '#00000010', offsetX: 0, offsetY: 2 })
                }
                
                if (!msg.isUser) {
                  Blank()
                }
              }
              .width('100%')
              .padding({ left: 12, right: 12, top: 6, bottom: 6 })
            }
          }, (msg: MsgItem): string => msg.id)
        }
        .width('100%')
        .layoutWeight(1)
        .backgroundColor('#F9FAFB')

        // 工具状态
        if (this.toolInfo.length > 0) {
          Text(this.toolInfo)
            .fontSize(13)
            .fontColor('#667EEA')
            .padding(8)
            .width('100%')
            .backgroundColor('#EEF2FF')
        }

        // 快捷操作
        if (this.showActions) {
          Column() {
            // 第一行
            Row() {
              Column() {
                Text('🧹')
                  .fontSize(24)
                Text('清空对话')
                  .fontSize(12)
                  .fontColor('#4B5563')
                  .margin({ top: 4 })
              }
              .width('25%')
              .padding(8)
              .backgroundColor('#F3F4F6')
              .borderRadius(12)
              .margin({ right: 4 })
              .onClick((): void => { this.doAction('clear') })

              Column() {
                Text('🧠')
                  .fontSize(24)
                Text('记忆检索')
                  .fontSize(12)
                  .fontColor('#4B5563')
                  .margin({ top: 4 })
              }
              .width('25%')
              .padding(8)
              .backgroundColor('#F3F4F6')
              .borderRadius(12)
              .margin({ left: 4, right: 4 })
              .onClick((): void => { this.doAction('memory') })

              Column() {
                Text('📋')
                  .fontSize(24)
                Text('任务列表')
                  .fontSize(12)
                  .fontColor('#4B5563')
                  .margin({ top: 4 })
              }
              .width('25%')
              .padding(8)
              .backgroundColor('#F3F4F6')
              .borderRadius(12)
              .margin({ left: 4, right: 4 })
              .onClick((): void => { this.doAction('tasks') })

              Column() {
                Text('🔄')
                  .fontSize(24)
                Text('演进报告')
                  .fontSize(12)
                  .fontColor('#4B5563')
                  .margin({ top: 4 })
              }
              .width('25%')
              .padding(8)
              .backgroundColor('#F3F4F6')
              .borderRadius(12)
              .margin({ left: 4 })
              .onClick((): void => { this.doAction('evolution') })
            }
            .width('100%')
            .margin({ bottom: 8 })

            // 第二行
            Row() {
              Column() {
                Text('📊')
                  .fontSize(24)
                Text('上下文')
                  .fontSize(12)
                  .fontColor('#4B5563')
                  .margin({ top: 4 })
              }
              .width('25%')
              .padding(8)
              .backgroundColor('#F3F4F6')
              .borderRadius(12)
              .margin({ right: 4 })
              .onClick((): void => { this.doAction('context') })

              Column() {
                Text('📁')
                  .fontSize(24)
                Text('文件列表')
                  .fontSize(12)
                  .fontColor('#4B5563')
                  .margin({ top: 4 })
              }
              .width('25%')
              .padding(8)
              .backgroundColor('#F3F4F6')
              .borderRadius(12)
              .margin({ left: 4, right: 4 })
              .onClick((): void => { this.doAction('files') })

              Column() {
                Text('🔍')
                  .fontSize(24)
                Text('搜索')
                  .fontSize(12)
                  .fontColor('#4B5563')
                  .margin({ top: 4 })
              }
              .width('25%')
              .padding(8)
              .backgroundColor('#F3F4F6')
              .borderRadius(12)
              .margin({ left: 4, right: 4 })
              .onClick((): void => { this.doAction('search') })

              Column() {
                Text('📝')
                  .fontSize(24)
                Text('创建笔记')
                  .fontSize(12)
                  .fontColor('#4B5563')
                  .margin({ top: 4 })
              }
              .width('25%')
              .padding(8)
              .backgroundColor('#F3F4F6')
              .borderRadius(12)
              .margin({ left: 4 })
              .onClick((): void => { this.doAction('note') })
            }
            .width('100%')
          }
          .width('100%')
          .padding(12)
          .backgroundColor('#FFFFFF')
          .borderRadius({ topLeft: 16, topRight: 16 })
          .shadow({ radius: 8, color: '#00000010', offsetX: 0, offsetY: -2 })
        }

        // 输入栏
        Row() {
          Button('⚡')
            .fontSize(16)
            .width(40)
            .height(40)
            .backgroundColor(this.showActions ? '#667EEA' : '#F3F4F6')
            .fontColor(this.showActions ? '#FFFFFF' : '#6B7280')
            .borderRadius(20)
            .onClick((): void => {
              this.showActions = !this.showActions
            })

          TextInput({ text: this.inputVal, placeholder: '输入消息...' })
            .layoutWeight(1)
            .height(40)
            .backgroundColor('#F3F4F6')
            .borderRadius(20)
            .padding({ left: 16, right: 16 })
            .margin({ left: 8, right: 8 })
            .onChange((v: string): void => {
              this.inputVal = v
            })
            .onSubmit((): void => {
              this.sendMsg()
            })

          Button('➤')
            .fontSize(16)
            .width(40)
            .height(40)
            .backgroundColor(this.loading ? '#D1D5DB' : '#667EEA')
            .fontColor('#FFFFFF')
            .borderRadius(20)
            .enabled(!this.loading)
            .onClick((): void => {
              this.sendMsg()
            })
        }
        .width('100%')
        .padding({ left: 12, right: 12, top: 8, bottom: 8 })
        .backgroundColor('#FFFFFF')
      }
    }
    .width('100%')
    .height('100%')
  }
}
