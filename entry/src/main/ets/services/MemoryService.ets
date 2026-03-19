// MemoryService - 分层记忆服务
// 让智能搭档越来越懂你的心
import { Logger } from '../utils/Logger'
import { generateId } from '../utils/TextFormatter'
import { common } from '@kit.AbilityKit'

// 记忆类型
export type MemoryType = 'short_term' | 'mid_term' | 'long_term'

// 记忆重要性
export type MemoryImportance = 'critical' | 'important' | 'normal' | 'trivial'

// 记忆条目
export class MemoryEntry {
  id: string = ''
  type: MemoryType = 'mid_term'
  category: string = ''
  key: string = ''
  content: string = ''
  importance: MemoryImportance = 'normal'
  accessCount: number = 0
  lastAccessed: string = ''
  createdAt: string = ''
  expiresAt: string = ''
  metadata: Map<string, string> = new Map()
}

// 记忆配置
export class MemoryConfig {
  shortTermMaxAge: number = 24 * 60 * 60 * 1000 // 1天
  midTermMaxAge: number = 30 * 24 * 60 * 60 * 1000 // 30天
  longTermMaxCount: number = 100
}

export class MemoryService {
  private memories: Map<string, MemoryEntry> = new Map()
  private config: MemoryConfig = new MemoryConfig()
  private initialized: boolean = false
  private context: common.UIAbilityContext | null = null

  async init(context: common.UIAbilityContext): Promise<void> {
    if (this.initialized) return
    this.context = context
    await this.cleanupExpiredMemories()
    this.initialized = true
    Logger.info('MemoryService initialized')
  }

  // 添加记忆
  async addMemory(
    category: string,
    key: string,
    content: string,
    type: MemoryType = 'mid_term',
    importance: MemoryImportance = 'normal'
  ): Promise<MemoryEntry> {
    const now = new Date().toISOString()
    const entry = new MemoryEntry()
    entry.id = generateId()
    entry.type = type
    entry.category = category
    entry.key = key
    entry.content = content
    entry.importance = importance
    entry.accessCount = 0
    entry.lastAccessed = now
    entry.createdAt = now
    entry.expiresAt = this.calculateExpiry(type)

    this.memories.set(entry.id, entry)
    Logger.info(`Memory added: [${type}] ${category}/${key}`)
    
    // 检查是否需要晋升
    await this.checkPromotion(entry)
    
    return entry
  }

  // 计算过期时间
  private calculateExpiry(type: MemoryType): string {
    const now = Date.now()
    switch (type) {
      case 'short_term':
        return new Date(now + this.config.shortTermMaxAge).toISOString()
      case 'mid_term':
        return new Date(now + this.config.midTermMaxAge).toISOString()
      case 'long_term':
        return '' // 长期记忆不过期
    }
  }

  // 检查记忆晋升（短期→中期→长期）
  private async checkPromotion(entry: MemoryEntry): Promise<void> {
    // 频繁访问的短期记忆晋升为中期
    if (entry.type === 'short_term' && entry.accessCount >= 3) {
      entry.type = 'mid_term'
      entry.expiresAt = this.calculateExpiry('mid_term')
      Logger.info(`Memory promoted to mid_term: ${entry.key}`)
    }

    // 高重要性且频繁访问的中期记忆晋升为长期
    if (entry.type === 'mid_term' && 
        entry.importance === 'critical' && 
        entry.accessCount >= 5) {
      entry.type = 'long_term'
      entry.expiresAt = ''
      Logger.info(`Memory promoted to long_term: ${entry.key}`)
    }
  }

  // 检索记忆
  async retrieveMemory(query: string, limit: number = 5): Promise<MemoryEntry[]> {
    const results: MemoryEntry[] = []
    const queryLower = query.toLowerCase()

    this.memories.forEach((entry: MemoryEntry) => {
      const keyMatch = entry.key.toLowerCase().includes(queryLower)
      const contentMatch = entry.content.toLowerCase().includes(queryLower)
      const categoryMatch = entry.category.toLowerCase().includes(queryLower)

      if (keyMatch || contentMatch || categoryMatch) {
        entry.accessCount++
        entry.lastAccessed = new Date().toISOString()
        results.push(entry)
      }
    })

    // 按重要性和访问次数排序
    results.sort((a: MemoryEntry, b: MemoryEntry): number => {
      const importanceOrder: Record<string, number> = {
        'critical': 0,
        'important': 1,
        'normal': 2,
        'trivial': 3
      }
      const impDiff = importanceOrder[a.importance] - importanceOrder[b.importance]
      if (impDiff !== 0) return impDiff
      return b.accessCount - a.accessCount
    })

    // 检查晋升
    const limited = results.slice(0, limit)
    for (const entry of limited) {
      await this.checkPromotion(entry)
    }

    return limited
  }

  // 获取指定分类的记忆
  getMemoriesByCategory(category: string): MemoryEntry[] {
    const result: MemoryEntry[] = []
    this.memories.forEach((entry: MemoryEntry) => {
      if (entry.category === category) {
        result.push(entry)
      }
    })
    return result
  }

  // 获取所有记忆
  getAllMemories(): MemoryEntry[] {
    const result: MemoryEntry[] = []
    this.memories.forEach((entry: MemoryEntry) => {
      result.push(entry)
    })
    return result
  }

  // 清理过期记忆
  private async cleanupExpiredMemories(): Promise<void> {
    const now = new Date()
    const toDelete: string[] = []

    this.memories.forEach((entry: MemoryEntry, id: string) => {
      if (entry.expiresAt.length > 0 && new Date(entry.expiresAt) < now) {
        toDelete.push(id)
      }
    })

    for (const id of toDelete) {
      this.memories.delete(id)
      Logger.info(`Memory expired and removed: ${id}`)
    }
  }

  // 格式化记忆用于显示
  formatMemoryList(memories: MemoryEntry[]): string {
    if (memories.length === 0) {
      return '🧠 暂无记忆'
    }

    const typeEmoji: Record<string, string> = {
      'short_term': '💨',
      'mid_term': '📝',
      'long_term': '💎'
    }

    const importanceEmoji: Record<string, string> = {
      'critical': '❗',
      'important': '⭐',
      'normal': '•',
      'trivial': '·'
    }

    let output = '🧠 记忆检索结果：\n\n'
    for (const entry of memories) {
      output += `${typeEmoji[entry.type]} ${importanceEmoji[entry.importance]} **${entry.key}**\n`
      output += `   📁 ${entry.category}\n`
      const contentPreview = entry.content.length > 100 
        ? entry.content.substring(0, 100) + '...' 
        : entry.content
      output += `   📄 ${contentPreview}\n`
      output += `   🔢 访问 ${entry.accessCount} 次\n\n`
    }
    return output
  }

  // 生成记忆摘要（用于注入系统提示词）
  generateMemorySummary(limit: number = 10): string {
    const important = this.getImportantMemories(limit)
    if (important.length === 0) return ''

    let summary = '\n## 关于用户的记忆\n'
    for (const entry of important) {
      summary += `- **${entry.key}**: ${entry.content}\n`
    }
    return summary
  }

  // 获取重要记忆
  private getImportantMemories(limit: number): MemoryEntry[] {
    const important: MemoryEntry[] = []
    this.memories.forEach((entry: MemoryEntry) => {
      if (entry.importance === 'critical' || entry.importance === 'important') {
        important.push(entry)
      }
    })
    important.sort((a: MemoryEntry, b: MemoryEntry): number => {
      return b.accessCount - a.accessCount
    })
    return important.slice(0, limit)
  }

  // 删除记忆
  async deleteMemory(id: string): Promise<boolean> {
    if (this.memories.has(id)) {
      this.memories.delete(id)
      Logger.info(`Memory deleted: ${id}`)
      return true
    }
    return false
  }

  // 更新记忆
  async updateMemory(id: string, content: string): Promise<boolean> {
    const entry = this.memories.get(id)
    if (entry) {
      entry.content = content
      entry.lastAccessed = new Date().toISOString()
      entry.accessCount++
      Logger.info(`Memory updated: ${id}`)
      return true
    }
    return false
  }
}

// 单例
export const memoryService = new MemoryService()
