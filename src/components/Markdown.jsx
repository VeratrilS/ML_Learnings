import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cx } from './ui';

const components = {
    a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
};

export default function Markdown({ children, streaming, className }) {
    return (
        <div className={cx('prose-ai', streaming && 'caret', className)}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{children || ''}</ReactMarkdown>
        </div>
    );
}
