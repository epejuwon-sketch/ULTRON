import { AuthUser } from "../lib/api";
import { DeviceProfile } from "../lib/device";
import { ModuleId } from "../catalog/navigation";

export interface AttachedFileRef {
  file_id: string;
  filename: string;
  mime_type: string;
  is_image?: boolean;
  size_bytes?: number;
}

export interface ModulePageProps {
  subPage: string;
  onSelectSubPage: (sub: string) => void;
  onNavigate: (moduleId: ModuleId, subPageId?: string) => void;
  user: AuthUser;
  device: DeviceProfile;
  pendingPrompt?: string;
  onClearPendingPrompt?: () => void;
  onSendToNeon?: (prompt: string) => void;
  pendingFiles?: AttachedFileRef[];
  onAttachFileToNeon?: (file: AttachedFileRef) => void;
  onClearPendingFiles?: () => void;
  initialShare?: { title: string; text: string; url: string } | null;
}
