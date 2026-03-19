// SkillEvolutionService - 技能自演进服务
// 自动识别智能体轨迹中的异常错误，实现 Skills 自主演进
import { Logger } from '../utils/Logger'
import { generateId } from '../utils/TextFormatter'

// 错误类型
export type ErrorType = 
  | 'tool_execution_failed'
  | 'invalid_input'
  | 'timeout'
  | 'api_error'
  | 'parsing_error'
  | 'unknown'

// 错误记录
export class ErrorRecord {
  id: string = ''
  type: ErrorType = 'unknown'
  toolName: string = ''
  input: string = ''
  errorMessage: string = ''
  stackTrace: string = ''
  timestamp: string = ''
  resolved: boolean = false
  resolution: string = ''
}

// 技能改进建议
export class SkillImprovement {
  id: string = ''
  skillName: string = ''
  issue: string = ''
  suggestion: string = ''
  priority: 'high' | 'medium' | 'low' = 'low'
  status: 'pending' | 'applied' | 'rejected' = 'pending'
  createdAt: string = ''
  appliedAt: string = ''
}

// 工具错误计数
class ToolErrorCount {
  name: string = ''
  count: number = 0
}

// 演进统计
export class EvolutionStats {
  totalErrors: number = 0
  resolvedErrors: number = 0
  improvementsSuggested: number = 0
  improvementsApplied: number = 0
  topErrorTools: string[] = []
  errorRate: number = 0
}

export class SkillEvolutionService {
  private errors: Map<string, ErrorRecord> = new Map()
  private improvements: Map<string, SkillImprovement> = new Map()
  private errorCounts: Map<string, number> = new Map()
  private initialized: boolean = false

  async init(): Promise<void> {
    if (this.initialized) return
    this.initialized = true
    Logger.info('SkillEvolutionService initialized')
  }

  // 记录错误
  async recordError(
    type: ErrorType,
    errorMessage: string,
    toolName: string = '',
    input: string = '',
    stackTrace: string = ''
  ): Promise<ErrorRecord> {
    const record = new ErrorRecord()
    record.id = generateId()
    record.type = type
    record.toolName = toolName
    record.input = input
    record.errorMessage = errorMessage
    record.stackTrace = stackTrace
    record.timestamp = new Date().toISOString()
    record.resolved = false

    this.errors.set(record.id, record)

    // 更新工具错误计数
    if (toolName.length > 0) {
      let count = 0
      if (this.errorCounts.has(toolName)) {
        count = this.errorCounts.get(toolName) || 0
      }
      count++
      this.errorCounts.set(toolName, count)

      // 如果同一工具错误次数过多，生成改进建议
      if (count >= 3) {
        await this.generateImprovement(toolName, type)
      }
    }

    Logger.warn(`Error recorded: [${type}] ${toolName} - ${errorMessage}`)
    return record
  }

  // 生成改进建议
  private async generateImprovement(toolName: string, errorType: ErrorType): Promise<SkillImprovement> {
    // 检查是否已有类似建议
    let existing: SkillImprovement | null = null
    this.improvements.forEach((imp: SkillImprovement) => {
      if (imp.skillName === toolName && imp.status === 'pending') {
        existing = imp
      }
    })

    if (existing) {
      return existing
    }

    // 分析错误模式并生成建议
    const toolErrors: ErrorRecord[] = []
    this.errors.forEach((e: ErrorRecord) => {
      if (e.toolName === toolName) {
        toolErrors.push(e)
      }
    })

    const improvement = new SkillImprovement()
    improvement.id = generateId()
    improvement.skillName = toolName
    improvement.issue = this.analyzeIssue(toolErrors)
    improvement.suggestion = this.generateSuggestion(toolName, errorType, toolErrors)
    improvement.priority = this.determinePriority(toolErrors)
    improvement.status = 'pending'
    improvement.createdAt = new Date().toISOString()

    this.improvements.set(improvement.id, improvement)
    Logger.info(`Improvement suggestion generated for ${toolName}`)
    
    return improvement
  }

  // 分析问题
  private analyzeIssue(errors: ErrorRecord[]): string {
    const errorTypes: Set<string> = new Set()
    for (const e of errors) {
      errorTypes.add(e.type)
    }
    
    const issues: string[] = []

    if (errorTypes.has('tool_execution_failed')) {
      issues.push('工具执行失败')
    }
    if (errorTypes.has('invalid_input')) {
      issues.push('输入参数无效')
    }
    if (errorTypes.has('timeout')) {
      issues.push('执行超时')
    }

    return issues.join('、') || '未知问题'
  }

  // 生成建议
  private generateSuggestion(
    toolName: string,
    errorType: ErrorType,
    errors: ErrorRecord[]
  ): string {
    switch (errorType) {
      case 'invalid_input':
        return `建议优化 ${toolName} 的输入验证逻辑，添加参数格式检查`
      case 'timeout':
        return `建议为 ${toolName} 添加超时重试机制或优化执行效率`
      case 'tool_execution_failed':
        return `建议检查 ${toolName} 的执行路径，增加错误处理和降级策略`
      case 'api_error':
        return `建议为 ${toolName} 添加 API 错误重试和备用方案`
      default:
        return `建议审查 ${toolName} 的整体实现`
    }
  }

  // 确定优先级
  private determinePriority(errors: ErrorRecord[]): 'high' | 'medium' | 'low' {
    const now = Date.now()
    let recentCount = 0
    for (const e of errors) {
      if (now - new Date(e.timestamp).getTime() < 24 * 60 * 60 * 1000) {
        recentCount++
      }
    }
    
    if (recentCount >= 5) return 'high'
    if (recentCount >= 2) return 'medium'
    return 'low'
  }

  // 标记错误已解决
  async resolveError(errorId: string, resolution: string): Promise<boolean> {
    const record = this.errors.get(errorId)
    if (record) {
      record.resolved = true
      record.resolution = resolution
      Logger.info(`Error ${errorId} resolved: ${resolution}`)
      return true
    }
    return false
  }

  // 应用改进建议
  async applyImprovement(improvementId: string): Promise<boolean> {
    const improvement = this.improvements.get(improvementId)
    if (improvement && improvement.status === 'pending') {
      improvement.status = 'applied'
      improvement.appliedAt = new Date().toISOString()
      
      // 重置该工具的错误计数
      this.errorCounts.set(improvement.skillName, 0)
      
      Logger.info(`Improvement ${improvementId} applied to ${improvement.skillName}`)
      return true
    }
    return false
  }

  // 获取统计信息
  getStats(): EvolutionStats {
    const stats = new EvolutionStats()
    stats.totalErrors = this.errors.size
    
    let resolvedCount = 0
    this.errors.forEach((e: ErrorRecord) => {
      if (e.resolved) resolvedCount++
    })
    stats.resolvedErrors = resolvedCount
    
    stats.improvementsSuggested = this.improvements.size
    
    let appliedCount = 0
    this.improvements.forEach((i: SkillImprovement) => {
      if (i.status === 'applied') appliedCount++
    })
    stats.improvementsApplied = appliedCount

    // 找出错误最多的工具
    const toolErrors: ToolErrorCount[] = []
    this.errorCounts.forEach((count: number, name: string) => {
      const item = new ToolErrorCount()
      item.name = name
      item.count = count
      toolErrors.push(item)
    })
    toolErrors.sort((a: ToolErrorCount, b: ToolErrorCount): number => {
      return b.count - a.count
    })
    
    for (let i = 0; i < 5 && i < toolErrors.length; i++) {
      stats.topErrorTools.push(toolErrors[i].name)
    }

    // 计算错误率
    stats.errorRate = stats.totalErrors > 0 
      ? (stats.resolvedErrors / stats.totalErrors) * 100 
      : 0

    return stats
  }

  // 获取待处理的改进建议
  getPendingImprovements(): SkillImprovement[] {
    const pending: SkillImprovement[] = []
    this.improvements.forEach((imp: SkillImprovement) => {
      if (imp.status === 'pending') {
        pending.push(imp)
      }
    })
    
    pending.sort((a: SkillImprovement, b: SkillImprovement): number => {
      const priorityOrder: Record<string, number> = {
        'high': 0,
        'medium': 1,
        'low': 2
      }
      return priorityOrder[a.priority] - priorityOrder[b.priority]
    })
    
    return pending
  }

  // 获取最近的错误
  getRecentErrors(limit: number = 10): ErrorRecord[] {
    const all: ErrorRecord[] = []
    this.errors.forEach((e: ErrorRecord) => {
      all.push(e)
    })
    
    all.sort((a: ErrorRecord, b: ErrorRecord): number => {
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    })
    
    return all.slice(0, limit)
  }

  // 生成演进报告
  generateReport(): string {
    const stats = this.getStats()
    const pending = this.getPendingImprovements()

    let report = '🔄 技能演进报告\n\n'
    report += `📊 统计信息\n`
    report += `- 总错误数：${stats.totalErrors}\n`
    report += `- 已解决：${stats.resolvedErrors}\n`
    report += `- 改进建议：${stats.improvementsSuggested}\n`
    report += `- 已应用：${stats.improvementsApplied}\n`
    report += `- 错误解决率：${stats.errorRate.toFixed(1)}%\n`

    if (stats.topErrorTools.length > 0) {
      report += `\n⚠️ 错误最多的工具\n`
      for (const tool of stats.topErrorTools) {
        const count = this.errorCounts.get(tool) || 0
        report += `- ${tool}: ${count} 次\n`
      }
    }

    if (pending.length > 0) {
      report += `\n💡 待处理的改进建议\n`
      for (const imp of pending) {
        const priorityEmoji: Record<string, string> = {
          'high': '🔴',
          'medium': '🟡',
          'low': '🟢'
        }
        report += `${priorityEmoji[imp.priority]} **${imp.skillName}**\n`
        report += `   问题：${imp.issue}\n`
        report += `   建议：${imp.suggestion}\n\n`
      }
    }

    return report
  }

  // 自动修复（简单的自动修复策略）
  async autoFix(): Promise<string[]> {
    const fixes: string[] = []
    const pending = this.getPendingImprovements()

    for (const imp of pending) {
      // 只自动应用低优先级的简单修复
      if (imp.priority === 'low') {
        await this.applyImprovement(imp.id)
        fixes.push(`已应用：${imp.skillName} - ${imp.suggestion}`)
      }
    }

    return fixes
  }
}

// 单例
export const skillEvolutionService = new SkillEvolutionService()
