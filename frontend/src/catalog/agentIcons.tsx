import React from "react";
import {
  Activity,
  AlertTriangle,
  Archive,
  Award,
  BarChart2,
  BarChart3,
  BookOpen,
  Bot,
  Box,
  Briefcase,
  Bug,
  Building2,
  Calculator,
  CheckCircle2,
  Cloud,
  Code2,
  Compass,
  Cpu,
  Database,
  FileCode,
  FileText,
  Film,
  FlaskConical,
  GitBranch,
  Globe,
  GraduationCap,
  HardDrive,
  Headphones,
  HeartHandshake,
  Image,
  Kanban,
  Landmark,
  Layers,
  Layout,
  LineChart,
  Lock,
  Mail,
  Megaphone,
  Mic,
  Monitor,
  Network,
  Package,
  Palette,
  PenTool,
  Presentation,
  Radar,
  Scale,
  Search,
  Server,
  Share2,
  Shield,
  ShieldAlert,
  Sparkles,
  Target,
  Terminal,
  TrendingUp,
  Truck,
  Users,
  Video,
  Workflow,
  type LucideIcon,
} from "lucide-react";

type IconComponent = LucideIcon;

/**
 * 60 distinct Lucide icon bindings mapped 1-to-1 to AGT-01 through AGT-60.
 * Zero emoji, zero duplicate generic fallbacks across the 60-agent registry.
 */
const AGENT_ICON_MAP: Record<string, IconComponent> = {
  "AGT-01": Compass,         // Executive Agent
  "AGT-02": Search,          // Research Agent
  "AGT-03": Code2,           // Coding Agent
  "AGT-04": Bug,             // Debugging Agent
  "AGT-05": Layers,          // Software Architecture Agent
  "AGT-06": Megaphone,       // Marketing Agent
  "AGT-07": Target,          // Sales Agent
  "AGT-08": Landmark,        // Finance Agent
  "AGT-09": Briefcase,       // Business Strategy Agent
  "AGT-10": Scale,           // Legal Research Agent
  "AGT-11": BarChart3,       // Data Analysis Agent
  "AGT-12": Layout,          // UI/UX Design Agent
  "AGT-13": Image,           // Image Generation Agent
  "AGT-14": Film,            // Video Production Agent
  "AGT-15": FileText,        // Professional Writing Agent
  "AGT-16": Mail,            // Communication Agent
  "AGT-17": CheckCircle2,    // Productivity Agent
  "AGT-18": Workflow,        // Automation Agent
  "AGT-19": HardDrive,       // Device Management Agent
  "AGT-20": Shield,          // Security Agent
  "AGT-21": BookOpen,        // Knowledge Management Agent
  "AGT-22": HeartHandshake,  // Customer Support Agent
  "AGT-23": BarChart2,       // Analytics Agent
  "AGT-24": Box,             // 3D Modelling Agent
  "AGT-25": Terminal,        // Testing Agent
  "AGT-26": Package,         // Product Management Agent
  "AGT-27": Kanban,          // Project Management Agent
  "AGT-28": Database,        // Database Engineering Agent
  "AGT-29": Network,         // API Engineering Agent
  "AGT-30": Cloud,           // Cloud Infrastructure Agent
  "AGT-31": GitBranch,       // DevOps Agent
  "AGT-32": Award,           // Quality Assurance Agent
  "AGT-33": ShieldAlert,     // Cybersecurity Analysis Agent
  "AGT-34": FileCode,        // Documentation Agent
  "AGT-35": Globe,           // Market Intelligence Agent
  "AGT-36": Radar,           // Competitor Intelligence Agent
  "AGT-37": Users,           // Customer Acquisition Agent
  "AGT-38": Activity,        // Customer Retention Agent
  "AGT-39": Sparkles,        // Advertising Strategy Agent
  "AGT-40": PenTool,         // Content Strategy Agent
  "AGT-41": Share2,          // Social Media Agent
  "AGT-42": Building2,       // Branding Agent
  "AGT-43": Palette,         // Graphic Design Agent
  "AGT-44": Presentation,    // Presentation Creation Agent
  "AGT-45": Headphones,      // Audio Processing Agent
  "AGT-46": Mic,             // Voice Engineering Agent
  "AGT-47": Video,           // Video Analysis Agent
  "AGT-48": Server,          // Data Engineering Agent
  "AGT-49": LineChart,       // Predictive Analytics Agent
  "AGT-50": FlaskConical,    // Scientific Research Agent
  "AGT-51": Calculator,      // Mathematics Agent
  "AGT-52": GraduationCap,   // Education & Tutoring Agent
  "AGT-53": Archive,         // Human Resources Agent
  "AGT-54": Monitor,         // Operations Management Agent
  "AGT-55": Truck,           // Supply Chain Analysis Agent
  "AGT-56": TrendingUp,      // Funding Research Agent
  "AGT-57": Lock,            // Investment Analysis Agent
  "AGT-58": AlertTriangle,   // Compliance Monitoring Agent
  "AGT-59": Cpu,             // System Diagnostics Agent
  "AGT-60": Bot,             // Agent Development & Evaluation Agent
};

export function AgentIcon({
  agentId,
  size = 16,
  className,
}: {
  agentId: string;
  size?: number;
  className?: string;
}) {
  const Icon = AGENT_ICON_MAP[agentId.toUpperCase()] || Bot;
  return <Icon size={size} className={className} />;
}
