import { thumbnailUrl } from "@/lib/api";
import type { DuplicateGroup, DuplicateMember } from "@/lib/types";
import {
  CheckCircle2,
  Copy,
  HardDrive,
  LoaderCircle,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

type DuplicateReviewDialogProps = {
  groups: DuplicateGroup[];
  loading: boolean;
  onClose: () => void;
  onDelete: (member: DuplicateMember) => void;
  open: boolean;
  sessionId?: string;
  writable: boolean;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DuplicateReviewDialog({
  groups,
  loading,
  onClose,
  onDelete,
  open,
  sessionId,
  writable,
}: DuplicateReviewDialogProps) {
  if (!open) return null;
  const duplicateFiles = groups.reduce((total, group) => total + group.members.length - 1, 0);
  const savings = groups.reduce((total, group) => total + group.potential_savings_bytes, 0);

  return (
    <div className="duplicate-scrim" role="presentation" onClick={onClose}>
      <section
        className="duplicate-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="重复照片检查"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span><Copy size={16} /> 重复照片检查</span>
            <small>感知哈希比较画面结构，颜色约束用于减少误判</small>
          </div>
          <button onClick={onClose} aria-label="关闭重复照片检查"><X size={18} /></button>
        </header>

        {loading ? (
          <div className="duplicate-loading"><LoaderCircle className="spin" size={24} /> 正在比较图片指纹…</div>
        ) : groups.length === 0 ? (
          <div className="duplicate-empty">
            <CheckCircle2 size={30} />
            <strong>没有发现近似重复照片</strong>
            <span>完全相同的文件已在导入时自动跳过。</span>
          </div>
        ) : (
          <>
            <div className="duplicate-summary">
              <div><strong>{groups.length}</strong><span>组相似照片</span></div>
              <div><strong>{duplicateFiles}</strong><span>个可检查副本</span></div>
              <div><strong>{formatBytes(savings)}</strong><span>预计可释放</span></div>
              <p><ShieldCheck size={14} /> {writable ? "只会删除 MuseLens 导入副本，不会触碰原始照片" : "当前图库仅供检查，不允许逐张删除"}</p>
            </div>
            <div className="duplicate-groups">
              {groups.map((group, groupIndex) => (
                <article className="duplicate-group" key={group.group_id}>
                  <div className="duplicate-group-heading">
                    <div><strong>相似组 {groupIndex + 1}</strong><span>{group.members.length} 张照片</span></div>
                    <span><HardDrive size={13} /> 可释放 {formatBytes(group.potential_savings_bytes)}</span>
                  </div>
                  <div className="duplicate-members">
                    {group.members.map((member) => (
                      <div className="duplicate-member" key={member.image_id}>
                        <div className="duplicate-image">
                          <img
                            src={thumbnailUrl(member.image_id, sessionId)}
                            alt={member.filename}
                            loading="lazy"
                          />
                          {member.recommended_keep && <span><ShieldCheck size={12} /> 建议保留</span>}
                        </div>
                        <div className="duplicate-member-meta">
                          <strong title={member.filename}>{member.filename}</strong>
                          <span>{member.width} × {member.height} · {formatBytes(member.size_bytes)}</span>
                          <small>
                            {member.recommended_keep
                              ? "组内分辨率与文件质量优先"
                              : `与保留项指纹距离 ${member.distance_to_representative} / 64`}
                          </small>
                        </div>
                        {writable && !member.recommended_keep && (
                          <button onClick={() => onDelete(member)}>
                            <Trash2 size={14} /> 删除导入副本
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
