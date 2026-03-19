// MarkdownRenderer - 简易 Markdown 渲染器
// 将 Markdown 文本转换为 ArkUI 组件

// Markdown 行类型
export type MdLineType = 'h1' | 'h2' | 'h3' | 'h4' | 'text' | 'code' | 'bullet' | 'number' | 'quote' | 'empty'

// 解析后的行
export class MdLine {
  type: MdLineType = 'text'
  content: string = ''
  level: number = 0
  codeBlock: boolean = false
}

// Markdown 解析器
export class MarkdownParser {
  // 解析 Markdown 文本
  static parse(text: string): MdLine[] {
    const lines: MdLine[] = []
    const rawLines = text.split('\n')
    let inCodeBlock = false
    let codeContent = ''

    for (const rawLine of rawLines) {
      const line = rawLine.trim()

      // 代码块处理
      if (line.startsWith('```')) {
        if (inCodeBlock) {
          // 结束代码块
          const mdLine = new MdLine()
          mdLine.type = 'code'
          mdLine.content = codeContent
          lines.push(mdLine)
          codeContent = ''
          inCodeBlock = false
        } else {
          // 开始代码块
          inCodeBlock = true
        }
        continue
      }

      if (inCodeBlock) {
        codeContent += rawLine + '\n'
        continue
      }

      // 空行
      if (line.length === 0) {
        const mdLine = new MdLine()
        mdLine.type = 'empty'
        lines.push(mdLine)
        continue
      }

      // 标题
      const headerMatch = line.match(/^(#{1,4})\s+(.+)$/)
      if (headerMatch) {
        const mdLine = new MdLine()
        const level = headerMatch[1].length
        mdLine.type = `h${level}` as MdLineType
        mdLine.content = headerMatch[2]
        mdLine.level = level
        lines.push(mdLine)
        continue
      }

      // 引用
      if (line.startsWith('>')) {
        const mdLine = new MdLine()
        mdLine.type = 'quote'
        mdLine.content = line.substring(1).trim()
        lines.push(mdLine)
        continue
      }

      // 无序列表
      const bulletMatch = line.match(/^[-*+]\s+(.+)$/)
      if (bulletMatch) {
        const mdLine = new MdLine()
        mdLine.type = 'bullet'
        mdLine.content = bulletMatch[1]
        lines.push(mdLine)
        continue
      }

      // 有序列表
      const numberMatch = line.match(/^(\d+)\.\s+(.+)$/)
      if (numberMatch) {
        const mdLine = new MdLine()
        mdLine.type = 'number'
        mdLine.content = numberMatch[2]
        mdLine.level = parseInt(numberMatch[1])
        lines.push(mdLine)
        continue
      }

      // 行内代码
      if (line.startsWith('`') && line.endsWith('`') && line.length > 2) {
        const mdLine = new MdLine()
        mdLine.type = 'code'
        mdLine.content = line.substring(1, line.length - 1)
        lines.push(mdLine)
        continue
      }

      // 普通文本
      const mdLine = new MdLine()
      mdLine.type = 'text'
      mdLine.content = rawLine
      lines.push(mdLine)
    }

    // 处理未闭合的代码块
    if (inCodeBlock && codeContent.length > 0) {
      const mdLine = new MdLine()
      mdLine.type = 'code'
      mdLine.content = codeContent
      lines.push(mdLine)
    }

    return lines
  }

  // 处理行内样式（粗体、斜体、行内代码）
  static formatInlineText(text: string): string {
    // 粗体 **text**
    text = text.replace(/\*\*(.+?)\*\*/g, '$1')
    // 斜体 *text* 或 _text_
    text = text.replace(/[*_](.+?)[*_]/g, '$1')
    // 行内代码 `code`
    text = text.replace(/`(.+?)`/g, '$1')
    // 链接 [text](url)
    text = text.replace(/\[(.+?)\]\((.+?)\)/g, '$1')
    return text
  }
}

// Markdown 样式配置
export class MdStyle {
  static getHeaderFontSize(level: number): number {
    switch (level) {
      case 1: return 24
      case 2: return 20
      case 3: return 18
      case 4: return 16
      default: return 16
    }
  }

  static getHeaderColor(level: number): string {
    switch (level) {
      case 1: return '#1a1a2e'
      case 2: return '#333333'
      case 3: return '#444444'
      case 4: return '#555555'
      default: return '#333333'
    }
  }

  static readonly textFontSize: number = 15
  static readonly textFontColor: string = '#333333'
  static readonly codeFontSize: number = 13
  static readonly codeFontColor: string = '#d63384'
  static readonly codeBgColor: string = '#f8f9fa'
  static readonly quoteFontColor: string = '#666666'
  static readonly quoteBorderColor: string = '#6C5CE7'
  static readonly bulletColor: string = '#6C5CE7'
}
