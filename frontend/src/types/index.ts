export interface ExtraSubject {
  name: string
  time: string
  days: string[]
}

export interface DashboardData {
  student: string
  today_timetable: TimetableDay | null
  extra_subjects: ExtraSubject[]
  summary_last: SummaryData | null
  summary_current: SummaryData | null
  summary_next: SummaryData | null
  komens: KomensData | null
  marks: MarksData | null
  prepare_today: PrepareData | null
  prepare_tomorrow: PrepareData | null
}

export interface TimetableDay {
  date: string
  day_type: string
  description: string | null
  is_school_day: boolean
  lessons: Lesson[]
}

export interface Lesson {
  abbrev: string
  name: string
  begin_time: string
  end_time: string
  teacher: string | null
  room: string | null
  theme: string | null
  is_changed: boolean
  change_description: string | null
}

export interface SummaryData {
  summary_text: string
  student_name: string
  week_type: string
  week_start: string
  week_end: string
  generated_at: string
}

export interface KomensData {
  unread_count: number
  received_count: number
  recent_messages: KomensMessage[]
}

export interface KomensMessage {
  id: string
  title: string
  sender: string | null
  date: string | null
  is_read: boolean
  text: string
  has_attachments: boolean
}

export interface MarksData {
  overall_average: number | null
  new_marks_count: number
  subjects: SubjectMarks[]
}

export interface SubjectMarks {
  name: string
  abbrev: string
  average: number | null
  marks_count: number
  new_marks: number
}

export interface PrepareData {
  preparation_text: string
  student_name: string
  target_date: string
  period: string
  generated_at: string
}

export interface GDriveReport {
  week_number: number
  content: string
  school_year: string
  fetched_at: string
  source_file: string
}

export interface PromptResponse {
  result: string
  resolved_variables: string[]
  generated_at: string
}

export interface PromptVariable {
  name: string
  category: string
  description: string
}

export interface LogEntry {
  timestamp: string
  category: string
  level: string
  message: string
  student: string | null
  details: Record<string, unknown> | null
}

export interface TaskStatus {
  task_name: string
  student: string
  interval_seconds: number
  last_run: string | null
  last_duration_ms: number | null
  last_status: string
  last_error: string | null
  next_run: string | null
  run_count: number
  error_count: number
}
