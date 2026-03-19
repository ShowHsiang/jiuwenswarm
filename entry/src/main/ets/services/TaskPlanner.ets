// TaskPlanner - 任务规划服务
// 为智能体装上"任务管理器"，做一个懂你的任务管家
import { Logger } from '../utils/Logger'
import { generateId } from '../utils/TextFormatter'

// 任务优先级
export type TaskPriority = 'high' | 'medium' | 'low'

// 任务状态
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled'

// 子任务
export class SubTask {
  id: string = ''
  description: string = ''
  status: TaskStatus = 'pending'
  dependencies: string[] = []
}

// 规划任务
export class PlannedTask {
  id: string = ''
  chatId: string = ''
  title: string = ''
  description: string = ''
  priority: TaskPriority = 'medium'
  status: TaskStatus = 'pending'
  subTasks: SubTask[] = []
  createdAt: string = ''
  updatedAt: string = ''
  scheduledAt: string = ''
  completedAt: string = ''
  tags: string[] = []
  context: string = ''
}

// 任务意图结果
export class TaskIntentResult {
  isTask: boolean = false
  taskType: 'new' | 'modify' | 'query' | 'cancel' | 'none' = 'none'
  taskInfo: TaskInfo | null = null
}

// 任务信息
export class TaskInfo {
  title: string = ''
  description: string = ''
  priority: TaskPriority = 'medium'
  scheduledAt: string = ''
  tags: string[] = []
}

// 任务规划器
export class TaskPlanner {
  private tasks: Map<string, PlannedTask> = new Map()
  private initialized: boolean = false

  async init(): Promise<void> {
    if (this.initialized) return
    this.initialized = true
    Logger.info('TaskPlanner initialized')
  }

  // 解析用户输入，识别任务意图
  parseTaskIntent(userMessage: string): TaskIntentResult {
    const result = new TaskIntentResult()
    const lowerMsg = userMessage.toLowerCase()
    
    // 检测新任务
    const newTaskPatterns = [
      /帮我(.+)/,
      /请(.+)/,
      /我要(.+)/,
      /需要(.+)/,
      /计划(.+)/,
      /安排(.+)/,
      /remind me to (.+)/i,
      /help me (.+)/i,
      /i need to (.+)/i
    ]

    for (const pattern of newTaskPatterns) {
      const match = userMessage.match(pattern)
      if (match) {
        result.isTask = true
        result.taskType = 'new'
        const info = new TaskInfo()
        info.description = match[1].trim()
        info.title = match[1].trim().substring(0, 50)
        result.taskInfo = info
        return result
      }
    }

    // 检测任务查询
    const queryPatterns = [
      /任务列表/,
      /待办/,
      /有什么任务/,
      /我的计划/,
      /what tasks/i,
      /my tasks/i,
      /to-?do/i
    ]

    for (const pattern of queryPatterns) {
      if (pattern.test(lowerMsg)) {
        result.isTask = true
        result.taskType = 'query'
        return result
      }
    }

    // 检测任务取消
    const cancelPatterns = [
      /取消(.+)/,
      /删除(.+)任务/,
      /cancel (.+)/i,
      /remove (.+) task/i
    ]

    for (const pattern of cancelPatterns) {
      const match = userMessage.match(pattern)
      if (match) {
        result.isTask = true
        result.taskType = 'cancel'
        const info = new TaskInfo()
        info.title = match[1].trim()
        result.taskInfo = info
        return result
      }
    }

    return result
  }

  // 创建任务
  async createTask(
    chatId: string,
    title: string,
    description: string,
    priority: TaskPriority = 'medium',
    subTasks: SubTask[] = [],
    tags: string[] = []
  ): Promise<PlannedTask> {
    const now = new Date().toISOString()
    const task = new PlannedTask()
    task.id = generateId()
    task.chatId = chatId
    task.title = title
    task.description = description
    task.priority = priority
    task.status = 'pending'
    task.subTasks = subTasks
    task.createdAt = now
    task.updatedAt = now
    task.tags = tags

    this.tasks.set(task.id, task)
    Logger.info(`Task created: ${task.id} - ${title}`)
    return task
  }

  // 智能拆解任务
  async decomposeTask(description: string): Promise<SubTask[]> {
    const subTasks: SubTask[] = []
    
    // 检测是否是复合任务（包含多个步骤）
    const steps = description.split(/[，,；;和与及]/)
    
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i].trim()
      if (step.length > 0) {
        const subTask = new SubTask()
        subTask.id = generateId()
        subTask.description = step
        subTask.status = 'pending'
        if (i > 0) {
          subTask.dependencies.push(subTasks[i - 1].id)
        }
        subTasks.push(subTask)
      }
    }

    return subTasks
  }

  // 更新任务状态
  async updateTaskStatus(taskId: string, status: TaskStatus): Promise<void> {
    const task = this.tasks.get(taskId)
    if (task) {
      task.status = status
      task.updatedAt = new Date().toISOString()
      if (status === 'completed') {
        task.completedAt = new Date().toISOString()
      }
      Logger.info(`Task ${taskId} status updated to ${status}`)
    }
  }

  // 获取任务列表
  getTasks(chatId: string = ''): PlannedTask[] {
    const allTasks: PlannedTask[] = []
    this.tasks.forEach((task: PlannedTask) => {
      if (chatId === '' || task.chatId === chatId) {
        allTasks.push(task)
      }
    })
    return allTasks
  }

  // 获取待处理任务
  getPendingTasks(chatId: string = ''): PlannedTask[] {
    const allTasks = this.getTasks(chatId)
    const pending: PlannedTask[] = []
    for (const task of allTasks) {
      if (task.status === 'pending') {
        pending.push(task)
      }
    }
    return pending
  }

  // 获取下一个可执行的子任务
  getNextExecutableSubTask(task: PlannedTask): SubTask | null {
    for (const subTask of task.subTasks) {
      if (subTask.status === 'pending') {
        // 检查依赖是否都完成
        let allDepsCompleted = true
        for (const depId of subTask.dependencies) {
          let found = false
          for (const s of task.subTasks) {
            if (s.id === depId && s.status === 'completed') {
              found = true
              break
            }
          }
          if (!found) {
            allDepsCompleted = false
            break
          }
        }
        if (allDepsCompleted) {
          return subTask
        }
      }
    }
    return null
  }

  // 优先级排序
  sortByPriority(tasks: PlannedTask[]): PlannedTask[] {
    const sorted = tasks.slice()
    sorted.sort((a: PlannedTask, b: PlannedTask): number => {
      const priorityOrder: Record<string, number> = {
        'high': 0,
        'medium': 1,
        'low': 2
      }
      const priorityDiff = priorityOrder[a.priority] - priorityOrder[b.priority]
      if (priorityDiff !== 0) return priorityDiff
      return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
    })
    return sorted
  }

  // 格式化任务列表用于显示
  formatTaskList(tasks: PlannedTask[]): string {
    if (tasks.length === 0) {
      return '📋 当前没有任务'
    }

    const priorityEmoji: Record<string, string> = {
      'high': '🔴',
      'medium': '🟡',
      'low': '🟢'
    }

    const statusEmoji: Record<string, string> = {
      'pending': '⏳',
      'in_progress': '🔄',
      'completed': '✅',
      'failed': '❌',
      'cancelled': '🚫'
    }

    let output = '📋 任务列表：\n\n'
    const sorted = this.sortByPriority(tasks)
    for (const task of sorted) {
      output += `${priorityEmoji[task.priority]} ${statusEmoji[task.status]} **${task.title}**\n`
      if (task.description !== task.title) {
        output += `   ${task.description}\n`
      }
      if (task.subTasks.length > 0) {
        let completed = 0
        for (const s of task.subTasks) {
          if (s.status === 'completed') completed++
        }
        output += `   📊 子任务: ${completed}/${task.subTasks.length}\n`
      }
      output += '\n'
    }
    return output
  }
}

// 单例
export const taskPlanner = new TaskPlanner()
