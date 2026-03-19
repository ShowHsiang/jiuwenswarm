// ContextSlimService - 上下文瘦身服务
// 上下文卸载技术保证智能体长时运行，守护你的账单
import { Logger } from '../utils/Logger'
import { ApiMessage } from '../models/Types'

// 摘要类型
export class MessageSummary {
  id: string = ''
  originalMessageCount: number = 0
  summary: string = ''
  keyPoints: string[] = []
  toolCallsSummary: string[] = []
  timestamp: string = ''
}

// 上下文统计
export class ContextStats {
  totalMessages: number = 0
  totalTokens: number = 0
  userMessages: number = 0
  assistantMessages: number = 0
  toolCalls: number = 0
  oldestMessageTime: string = ''
  newestMessageTime: string = ''
}

// 瘦身配置
export class SlimConfig {
  maxMessages: number = 50
  maxTokens: number = 32000
  summaryThreshold: number = 30
  preserveRecent: number = 10
}

// 瘦身结果
export class SlimResult {
  slimmed: ApiMessage[] = []
  summary: MessageSummary | null = null
}

export class ContextSlimService {
  private summaries: MessageSummary[] = []
  private config: SlimConfig = new SlimConfig()
  private initialized: boolean = false

  async init(): Promise<void> {
    if (this.initialized) return
    this.initialized = true
    Logger.info('ContextSlimService initialized')
  }

  // 分析上下文统计
  analyzeContext(messages: ApiMessage[]): ContextStats {
    const stats = new ContextStats()
    
    for (const msg of messages) {
      // 简单估算 token 数（中文约 1.5 字符/token，英文约 4 字符/token）
      const content = msg.content || ''
      const tokenEstimate = Math.ceil(content.length / 2)
      stats.totalTokens += tokenEstimate

      switch (msg.role) {
        case 'user':
          stats.userMessages++
          break
        case 'assistant':
          stats.assistantMessages++
          if (msg.toolCalls) {
            stats.toolCalls += msg.toolCalls.length
          }
          break
        case 'tool':
          stats.toolCalls++
          break
      }
    }

    stats.totalMessages = messages.length
    return stats
  }

  // 检查是否需要瘦身
  needsSlimming(messages: ApiMessage[]): boolean {
    const stats = this.analyzeContext(messages)
    return (
      stats.totalMessages > this.config.maxMessages ||
      stats.totalTokens > this.config.maxTokens
    )
  }

  // 执行上下文瘦身
  async slimContext(messages: ApiMessage[]): Promise<SlimResult> {
    const result = new SlimResult()
    
    if (!this.needsSlimming(messages)) {
      result.slimmed = messages
      return result
    }

    Logger.info('Context slimming started...')
    
    // 保留系统消息
    const systemMessages: ApiMessage[] = []
    for (const msg of messages) {
      if (msg.role === 'system') {
        systemMessages.push(msg)
      }
    }
    
    // 保留最近的消息
    const recentStart = messages.length - this.config.preserveRecent
    const recentMessages: ApiMessage[] = []
    for (let i = Math.max(0, recentStart); i < messages.length; i++) {
      recentMessages.push(messages[i])
    }
    
    // 需要压缩的消息
    const startIdx = systemMessages.length
    const endIdx = messages.length - this.config.preserveRecent
    const toCompress: ApiMessage[] = []
    for (let i = startIdx; i < endIdx && i < messages.length; i++) {
      toCompress.push(messages[i])
    }

    if (toCompress.length === 0) {
      result.slimmed = messages
      return result
    }

    // 创建摘要
    const summary = await this.createSummary(toCompress)
    this.summaries.push(summary)
    result.summary = summary

    // 构建新的上下文
    const summaryMsg: ApiMessage = {
      role: 'system',
      content: this.formatSummaryForContext(summary)
    }

    result.slimmed = []
    // 添加系统消息
    for (const msg of systemMessages) {
      result.slimmed.push(msg)
    }
    // 添加摘要
    result.slimmed.push(summaryMsg)
    // 添加最近消息
    for (const msg of recentMessages) {
      result.slimmed.push(msg)
    }

    Logger.info(`Context slimmed: ${messages.length} → ${result.slimmed.length} messages`)
    
    return result
  }

  // 创建消息摘要
  private async createSummary(messages: ApiMessage[]): Promise<MessageSummary> {
    const summary = new MessageSummary()
    summary.id = `summary_${Date.now()}`
    summary.originalMessageCount = messages.length
    summary.timestamp = new Date().toISOString()
    
    let totalContent = ''

    for (const msg of messages) {
      const content = msg.content || ''
      totalContent += content + '\n'

      // 提取关键点（简单实现）
      const sentences = content.split(/[。！？.!?]/)
      for (const sentence of sentences) {
        if (sentence.length > 10 && sentence.length < 100) {
          summary.keyPoints.push(sentence.trim())
        }
      }

      // 提取工具调用
      if (msg.toolCalls) {
        for (const tc of msg.toolCalls) {
          // 去重
          let found = false
          for (const existing of summary.toolCallsSummary) {
            if (existing === tc.function.name) {
              found = true
              break
            }
          }
          if (!found) {
            summary.toolCallsSummary.push(tc.function.name)
          }
        }
      }
    }

    // 限制关键点数量
    while (summary.keyPoints.length > 10) {
      summary.keyPoints.pop()
    }
    while (summary.toolCallsSummary.length > 10) {
      summary.toolCallsSummary.pop()
    }

    summary.summary = this.generateBriefSummary(totalContent)
    return summary
  }

  // 生成简要摘要
  private generateBriefSummary(content: string): string {
    // 简单实现：取前 500 字符
    const truncated = content.substring(0, 500)
    return `对话摘要：${truncated}${content.length > 500 ? '...' : ''}`
  }

  // 格式化摘要用于上下文
  private formatSummaryForContext(summary: MessageSummary): string {
    let ctx = `[历史对话摘要 - ${summary.originalMessageCount} 条消息]\n`
    ctx += summary.summary + '\n'
    
    if (summary.keyPoints.length > 0) {
      ctx += '\n关键要点：\n'
      const limit = Math.min(5, summary.keyPoints.length)
      for (let i = 0; i < limit; i++) {
        ctx += `- ${summary.keyPoints[i]}\n`
      }
    }

    if (summary.toolCallsSummary.length > 0) {
      ctx += `\n使用的工具：`
      for (let i = 0; i < summary.toolCallsSummary.length; i++) {
        if (i > 0) ctx += ', '
        ctx += summary.toolCallsSummary[i]
      }
      ctx += '\n'
    }

    return ctx
  }

  // 获取所有摘要
  getSummaries(): MessageSummary[] {
    return this.summaries
  }

  // 获取上下文使用统计
  getUsageReport(messages: ApiMessage[]): string {
    const stats = this.analyzeContext(messages)
    const summariesCount = this.summaries.length

    let report = '📊 上下文使用报告\n\n'
    report += `消息总数：${stats.totalMessages}\n`
    report += `估算 Token：${stats.totalTokens}\n`
    report += `用户消息：${stats.userMessages}\n`
    report += `助手消息：${stats.assistantMessages}\n`
    report += `工具调用：${stats.toolCalls}\n`
    report += `压缩摘要：${summariesCount}\n`

    const usagePercent = Math.round((stats.totalTokens / this.config.maxTokens) * 100)
    report += `\n上下文使用率：${usagePercent}%`

    if (usagePercent > 80) {
      report += ' ⚠️ 接近上限，建议清理'
    } else if (usagePercent > 60) {
      report += ' 📈 使用较多'
    } else {
      report += ' ✅ 正常'
    }

    return report
  }

  // 更新配置
  updateConfig(maxMessages: number, maxTokens: number): void {
    this.config.maxMessages = maxMessages
    this.config.maxTokens = maxTokens
    Logger.info('ContextSlimService config updated')
  }
}

// 单例
export const contextSlimService = new ContextSlimService()
