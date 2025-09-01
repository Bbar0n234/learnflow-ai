import namesMap from '../config/names_map.json';

interface NamesMap {
  files: Record<string, string>;
  folders: Record<string, string>;
  patterns: Record<string, string>;
}

export class ConfigService {
  private static namesMap = namesMap as NamesMap;

  /**
   * Get display name for a file path
   * @param filePath - The file path to get display name for
   * @returns User-friendly display name
   */
  static getDisplayName(filePath: string): string {
    // Check direct mapping
    const filename = filePath.split('/').pop() || filePath;
    if (this.namesMap.files[filename]) {
      return this.namesMap.files[filename];
    }
    
    // Check patterns (e.g., answer_001.md)
    for (const [pattern, template] of Object.entries(this.namesMap.patterns)) {
      const regex = new RegExp(pattern);
      const match = filename.match(regex);
      if (match) {
        // Extract number from filename
        const numberMatch = filename.match(/\d+/);
        if (numberMatch) {
          const number = parseInt(numberMatch[0], 10);
          return template.replace('{{number}}', number.toString());
        }
      }
    }
    
    // Check if file is in a special folder
    const pathParts = filePath.split('/');
    if (pathParts.length > 1) {
      const folder = pathParts[pathParts.length - 2];
      if (this.namesMap.folders[folder]) {
        return `${this.namesMap.folders[folder]} - ${filename}`;
      }
    }
    
    // Fallback - return original filename
    return filename;
  }
  
  /**
   * Get display name for a folder
   * @param folderPath - The folder path to get display name for
   * @returns User-friendly display name
   */
  static getFolderDisplayName(folderPath: string): string {
    // Get the last part of the folder path
    const folderName = folderPath.split('/').pop() || folderPath;
    
    // Check folder mapping
    if (this.namesMap.folders[folderName]) {
      return this.namesMap.folders[folderName];
    }
    
    // Fallback - return original folder name
    return folderName;
  }
  
  /**
   * Deduplicate names by adding counters
   * @param items - Array of items with names
   * @returns Map of original name to deduplicated name
   */
  static deduplicateNames<T extends { name: string }>(items: T[]): Map<T, string> {
    const result = new Map<T, string>();
    const counts = new Map<string, number>();
    
    items.forEach(item => {
      const name = item.name;
      const count = counts.get(name) || 0;
      counts.set(name, count + 1);
      
      if (count === 0) {
        result.set(item, name);
      } else {
        result.set(item, `${name} (${count + 1})`);
      }
    });
    
    return result;
  }
  
  /**
   * Get display name for session
   * @param session - Session object with display_name and input_content
   * @returns Display name or fallback to input_content
   */
  static getSessionDisplayName(session: { display_name?: string | null; input_content?: string }): string {
    if (session.display_name) {
      return session.display_name;
    }
    
    if (!session.input_content) {
      return 'Unnamed Session';
    }
    
    // Fallback: use first 50 characters of input_content
    const maxLength = 50;
    if (session.input_content.length <= maxLength) {
      return session.input_content;
    }
    
    return session.input_content.substring(0, maxLength) + '...';
  }
  
  /**
   * Group files by folder structure
   * @param files - Array of file paths
   * @returns Grouped files structure
   */
  static groupFilesByFolder(files: string[]): Map<string, string[]> {
    const grouped = new Map<string, string[]>();
    
    files.forEach(file => {
      const parts = file.split('/');
      if (parts.length === 1) {
        // Root level file
        const rootFiles = grouped.get('root') || [];
        rootFiles.push(file);
        grouped.set('root', rootFiles);
      } else {
        // File in folder
        const folder = parts.slice(0, -1).join('/');
        const folderFiles = grouped.get(folder) || [];
        folderFiles.push(file);
        grouped.set(folder, folderFiles);
      }
    });
    
    return grouped;
  }
}