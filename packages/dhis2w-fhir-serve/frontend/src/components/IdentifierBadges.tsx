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
            {/* A badge value can be arbitrarily long - a DHIS2 attribute value is whatever the
                instance stored - and the inspector rail is the narrowest surface these land on.
                So the chip may grow in height and its value break anywhere, because a rail that
                scrolls sideways for one chip hides everything else it holds. */}
            {badges.map((badge) => (
                <Badge
                    key={`${badge.label}-${badge.value}`}
                    variant="outline"
                    className="text-muted-foreground h-auto max-w-full gap-1 font-mono text-[10px] font-normal whitespace-normal"
                >
                    <span className="shrink-0 opacity-70">{badge.label}</span>
                    <span className="min-w-0 break-all">{badge.value}</span>
                </Badge>
            ))}
        </div>
    )
}
