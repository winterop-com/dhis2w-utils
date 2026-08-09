import { Badge } from '@/components/ui/badge'
import type { IdentifierBadge } from '@/lib/terminology'

/**
 * The DHIS2 identifiers a generated artifact carries, or a stated absence.
 *
 * This is the thread back to DHIS2. Every generated resource carries the uid - and where the
 * object had one, the code - of the DHIS2 object it came from, under a system that says which
 * kind of object that was (`id/option-set`, `code/program`). Showing the system tail beside the
 * value is what tells a uid identifier apart from a code identifier without reading the url.
 */
export function IdentifierBadges({ badges }: { badges: IdentifierBadge[] }) {
    if (badges.length === 0) return <span className="text-muted-foreground text-xs">-</span>
    return (
        <div className="flex flex-wrap gap-1">
            {badges.map((badge) => (
                <Badge
                    key={`${badge.label}-${badge.value}`}
                    variant="outline"
                    className="text-muted-foreground gap-1 font-mono text-[10px] font-normal"
                >
                    <span className="opacity-70">{badge.label}</span>
                    {badge.value}
                </Badge>
            ))}
        </div>
    )
}
