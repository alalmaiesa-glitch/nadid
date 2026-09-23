export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      analysis_runs: {
        Row: {
          completed_at: string | null
          engine_manifest: Json
          id: string
          metrics: Json
          run_type: string
          started_at: string
          state: string
          version_id: string
        }
        Insert: {
          completed_at?: string | null
          engine_manifest?: Json
          id?: string
          metrics?: Json
          run_type: string
          started_at?: string
          state: string
          version_id: string
        }
        Update: {
          completed_at?: string | null
          engine_manifest?: Json
          id?: string
          metrics?: Json
          run_type?: string
          started_at?: string
          state?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "analysis_runs_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      document_chunks: {
        Row: {
          chunk_key: string
          chunk_text: string
          created_at: string
          id: string
          node_keys: string[]
          search_vector: unknown
          sequence_no: number
          token_estimate: number
          version_id: string
        }
        Insert: {
          chunk_key: string
          chunk_text: string
          created_at?: string
          id?: string
          node_keys?: string[]
          search_vector?: unknown
          sequence_no: number
          token_estimate?: number
          version_id: string
        }
        Update: {
          chunk_key?: string
          chunk_text?: string
          created_at?: string
          id?: string
          node_keys?: string[]
          search_vector?: unknown
          sequence_no?: number
          token_estimate?: number
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "document_chunks_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      document_memory: {
        Row: {
          built_at: string | null
          chunk_count: number
          engine_manifest: Json
          headings: Json
          protected_count: number
          state: string
          updated_at: string
          version_id: string
        }
        Insert: {
          built_at?: string | null
          chunk_count?: number
          engine_manifest?: Json
          headings?: Json
          protected_count?: number
          state?: string
          updated_at?: string
          version_id: string
        }
        Update: {
          built_at?: string | null
          chunk_count?: number
          engine_manifest?: Json
          headings?: Json
          protected_count?: number
          state?: string
          updated_at?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "document_memory_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: true
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      document_nodes: {
        Row: {
          content_hash: string | null
          created_at: string
          id: string
          logical_node_key: string
          metadata: Json
          node_type: string
          normalized_text: string | null
          parent_id: string | null
          sequence_no: number
          source_anchor: Json
          text: string
          version_id: string
        }
        Insert: {
          content_hash?: string | null
          created_at?: string
          id?: string
          logical_node_key: string
          metadata?: Json
          node_type: string
          normalized_text?: string | null
          parent_id?: string | null
          sequence_no: number
          source_anchor?: Json
          text: string
          version_id: string
        }
        Update: {
          content_hash?: string | null
          created_at?: string
          id?: string
          logical_node_key?: string
          metadata?: Json
          node_type?: string
          normalized_text?: string | null
          parent_id?: string | null
          sequence_no?: number
          source_anchor?: Json
          text?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "document_nodes_parent_id_fkey"
            columns: ["parent_id"]
            isOneToOne: false
            referencedRelation: "document_nodes"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_nodes_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      document_versions: {
        Row: {
          change_summary: Json
          created_at: string
          document_id: string
          engine_manifest: Json
          id: string
          is_source: boolean
          parent_version_id: string | null
          source_sha256: string | null
          status: string
          storage_path: string | null
          version_no: number
        }
        Insert: {
          change_summary?: Json
          created_at?: string
          document_id: string
          engine_manifest?: Json
          id?: string
          is_source?: boolean
          parent_version_id?: string | null
          source_sha256?: string | null
          status?: string
          storage_path?: string | null
          version_no: number
        }
        Update: {
          change_summary?: Json
          created_at?: string
          document_id?: string
          engine_manifest?: Json
          id?: string
          is_source?: boolean
          parent_version_id?: string | null
          source_sha256?: string | null
          status?: string
          storage_path?: string | null
          version_no?: number
        }
        Relationships: [
          {
            foreignKeyName: "document_versions_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_versions_parent_version_id_fkey"
            columns: ["parent_version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      documents: {
        Row: {
          created_at: string
          filename: string
          id: string
          owner_id: string | null
          paragraph_count: number
          source_type: string
          status: string
          storage_path: string | null
          title: string
          updated_at: string
          word_count: number
        }
        Insert: {
          created_at?: string
          filename: string
          id?: string
          owner_id?: string | null
          paragraph_count?: number
          source_type?: string
          status?: string
          storage_path?: string | null
          title: string
          updated_at?: string
          word_count?: number
        }
        Update: {
          created_at?: string
          filename?: string
          id?: string
          owner_id?: string | null
          paragraph_count?: number
          source_type?: string
          status?: string
          storage_path?: string | null
          title?: string
          updated_at?: string
          word_count?: number
        }
        Relationships: []
      }
      fact_assertions: {
        Row: {
          authority: string
          canonical_value: string
          claim_key: string
          client_fact_id: string
          confidence: number
          context_text: string
          created_at: string
          fact_type: string
          id: string
          node_key: string
          surface_value: string
          version_id: string
        }
        Insert: {
          authority?: string
          canonical_value: string
          claim_key: string
          client_fact_id: string
          confidence?: number
          context_text?: string
          created_at?: string
          fact_type: string
          id?: string
          node_key: string
          surface_value: string
          version_id: string
        }
        Update: {
          authority?: string
          canonical_value?: string
          claim_key?: string
          client_fact_id?: string
          confidence?: number
          context_text?: string
          created_at?: string
          fact_type?: string
          id?: string
          node_key?: string
          surface_value?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "fact_assertions_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      fact_conflicts: {
        Row: {
          claim_key: string
          client_conflict_id: string
          confidence: number
          created_at: string
          fact_ids: string[]
          id: string
          resolved_at: string | null
          status: string
          values_found: string[]
          version_id: string
        }
        Insert: {
          claim_key: string
          client_conflict_id: string
          confidence?: number
          created_at?: string
          fact_ids?: string[]
          id?: string
          resolved_at?: string | null
          status?: string
          values_found?: string[]
          version_id: string
        }
        Update: {
          claim_key?: string
          client_conflict_id?: string
          confidence?: number
          created_at?: string
          fact_ids?: string[]
          id?: string
          resolved_at?: string | null
          status?: string
          values_found?: string[]
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "fact_conflicts_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      memory_terms: {
        Row: {
          created_at: string
          id: string
          node_keys: string[]
          occurrence_count: number
          term: string
          version_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          node_keys?: string[]
          occurrence_count?: number
          term: string
          version_id: string
        }
        Update: {
          created_at?: string
          id?: string
          node_keys?: string[]
          occurrence_count?: number
          term?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "memory_terms_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      protected_spans: {
        Row: {
          canonical_value: Json
          client_fact_id: string | null
          confidence: number
          created_at: string
          id: string
          lock_mode: string
          lock_policy: string
          node_id: string | null
          span_type: string
          surface_text: string
          validator_key: string
          version_id: string
        }
        Insert: {
          canonical_value?: Json
          client_fact_id?: string | null
          confidence?: number
          created_at?: string
          id?: string
          lock_mode?: string
          lock_policy?: string
          node_id?: string | null
          span_type: string
          surface_text: string
          validator_key: string
          version_id: string
        }
        Update: {
          canonical_value?: Json
          client_fact_id?: string | null
          confidence?: number
          created_at?: string
          id?: string
          lock_mode?: string
          lock_policy?: string
          node_id?: string | null
          span_type?: string
          surface_text?: string
          validator_key?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "protected_spans_node_id_fkey"
            columns: ["node_id"]
            isOneToOne: false
            referencedRelation: "document_nodes"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "protected_spans_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      suggestions: {
        Row: {
          category: string
          client_suggestion_id: string | null
          confidence: number
          created_at: string
          evidence: Json
          explanation: string
          id: string
          node_id: string | null
          original_text: string
          replacement_text: string | null
          source_engine: string
          status: string
          title: string
          version_id: string
        }
        Insert: {
          category: string
          client_suggestion_id?: string | null
          confidence?: number
          created_at?: string
          evidence?: Json
          explanation: string
          id?: string
          node_id?: string | null
          original_text: string
          replacement_text?: string | null
          source_engine?: string
          status?: string
          title: string
          version_id: string
        }
        Update: {
          category?: string
          client_suggestion_id?: string | null
          confidence?: number
          created_at?: string
          evidence?: Json
          explanation?: string
          id?: string
          node_id?: string | null
          original_text?: string
          replacement_text?: string | null
          source_engine?: string
          status?: string
          title?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "suggestions_node_id_fkey"
            columns: ["node_id"]
            isOneToOne: false
            referencedRelation: "document_nodes"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "suggestions_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      search_document_chunks: {
        Args: { p_limit?: number; p_query: string; p_version_id: string }
        Returns: {
          chunk_key: string
          chunk_text: string
          node_keys: string[]
          rank: number
          sequence_no: number
          token_estimate: number
        }[]
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
