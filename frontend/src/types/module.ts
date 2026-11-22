import { AuthUser } from "../lib/api";
import { DeviceProfile } from "../lib/device";
import { ModuleId } from "../catalog/navigation";

export interface ModulePageProps {
  subPage: string;
  onSelectSubPage: (sub: string) => void;
  onNavigate: (moduleId: ModuleId, subPageId?: string) => void;
  user: AuthUser;
  device: DeviceProfile;
  pendingPrompt?: string;
  onClearPendingPrompt?: () => void;
  onSendToNeon?: (prompt: string) => void;
  initialShare?: { title: string; text: string; url: string } | null;
}
